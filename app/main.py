from __future__ import annotations

import math
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import ezdxf
import ezdxf.path
import fitz
from ezdxf.entities import DXFGraphic
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ROOT_DIR.parent
STORAGE_DIR = PROJECT_DIR / "converted_files"
PAGE_WIDTH = 842
PAGE_HEIGHT = 595
PAGE_MARGIN = 36
FLATTENING_DISTANCE = 0.05

app = FastAPI(title="DXF to PDF Converter")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=ROOT_DIR / "templates")


ACAD_COLORS = {
    1: (255 / 255, 0 / 255, 0 / 255),
    2: (255 / 255, 255 / 255, 0 / 255),
    3: (0 / 255, 255 / 255, 0 / 255),
    4: (0 / 255, 255 / 255, 255 / 255),
    5: (0 / 255, 0 / 255, 255 / 255),
    6: (255 / 255, 0 / 255, 255 / 255),
    7: (0 / 255, 0 / 255, 0 / 255),
    8: (128 / 255, 128 / 255, 128 / 255),
    9: (192 / 255, 192 / 255, 192 / 255),
    12: (189 / 255, 0 / 255, 0 / 255),
}

DEFAULT_LAYER_STYLES = [
    {"match": "cut", "color": "#ff0000", "width": 1, "dash": "solid"},
    {"match": "Board", "color": "#000000", "width": 0.5, "dash": "dashed"},
    {"match": "big", "color": "#008000", "width": 1, "dash": "solid"},
    {"match": "ric", "color": "#0000ff", "width": 1, "dash": "solid"},
    {"match": "prf", "color": "#008000", "width": 1, "dash": "dashed"},
    {"match": "text", "color": "#808080", "width": 0.5, "dash": "solid"},
]


@dataclass
class LayerStyle:
    match: str
    color: tuple[float, float, float]
    width: float
    dash: str


@dataclass
class ConversionStats:
    layer_lengths: dict[str, float]
    total_cut_length: float


class Bounds:
    def __init__(self) -> None:
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf

    def add_point(self, x: float, y: float) -> None:
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    @property
    def is_empty(self) -> bool:
        return not all(math.isfinite(value) for value in (self.min_x, self.min_y, self.max_x, self.max_y))

    @property
    def width(self) -> float:
        return max(self.max_x - self.min_x, 1e-9)

    @property
    def height(self) -> float:
        return max(self.max_y - self.min_y, 1e-9)


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        return ACAD_COLORS[7]
    try:
        return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)
    except ValueError:
        return ACAD_COLORS[7]


def parse_layer_styles(raw_styles: str | None) -> list[LayerStyle]:
    source = DEFAULT_LAYER_STYLES
    if raw_styles:
        try:
            loaded = json.loads(raw_styles)
            if isinstance(loaded, list):
                source = loaded
        except json.JSONDecodeError:
            source = DEFAULT_LAYER_STYLES

    styles = []
    for item in source:
        if not isinstance(item, dict) or not str(item.get("match", "")).strip():
            continue
        styles.append(
            LayerStyle(
                match=str(item.get("match", "")).strip(),
                color=hex_to_rgb(str(item.get("color", "#000000"))),
                width=max(float(item.get("width", 0.7) or 0.7), 0.1),
                dash="dashed" if str(item.get("dash", "solid")).lower() == "dashed" else "solid",
            )
        )
    return styles


def entity_color(entity: DXFGraphic) -> tuple[float, float, float]:
    color_index = int(entity.dxf.color or 7)
    return ACAD_COLORS.get(color_index, ACAD_COLORS[7])


def entity_style(entity: DXFGraphic, layer_styles: list[LayerStyle]) -> LayerStyle:
    layer = str(entity.dxf.layer or "")
    layer_lower = layer.lower()
    for style in layer_styles:
        if style.match.lower() in layer_lower:
            return style
    return LayerStyle(match="", color=entity_color(entity), width=0.7, dash="solid")


def path_to_points(entity: DXFGraphic) -> list[tuple[float, float]]:
    path = ezdxf.path.make_path(entity)
    return [(float(point.x), float(point.y)) for point in path.flattening(distance=FLATTENING_DISTANCE)]


def iter_entity_paths(entity: DXFGraphic) -> Iterable[list[tuple[float, float]]]:
    entity_type = entity.dxftype()
    if entity_type in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
        try:
            points = path_to_points(entity)
        except TypeError:
            points = []
        if len(points) >= 2:
            yield points


def draw_entity_path(page: fitz.Page, entity: DXFGraphic, bounds: Bounds, scale: float, style: LayerStyle) -> None:
    entity_type = entity.dxftype()
    if entity_type not in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
        return

    try:
        path = ezdxf.path.make_path(entity)
    except TypeError:
        return

    shape = page.new_shape()
    current = convert_point(float(path.start.x), float(path.start.y), bounds, scale)
    for command in path:
        command_name = command.__class__.__name__
        if command_name == "LineTo":
            end = convert_point(float(command.end.x), float(command.end.y), bounds, scale)
            shape.draw_line(current, end)
            current = end
        elif command_name == "Curve4To":
            ctrl1 = convert_point(float(command.ctrl1.x), float(command.ctrl1.y), bounds, scale)
            ctrl2 = convert_point(float(command.ctrl2.x), float(command.ctrl2.y), bounds, scale)
            end = convert_point(float(command.end.x), float(command.end.y), bounds, scale)
            shape.draw_bezier(current, ctrl1, ctrl2, end)
            current = end
        elif command_name == "Curve3To":
            ctrl = convert_point(float(command.ctrl.x), float(command.ctrl.y), bounds, scale)
            end = convert_point(float(command.end.x), float(command.end.y), bounds, scale)
            ctrl1 = fitz.Point(current.x + (2 / 3) * (ctrl.x - current.x), current.y + (2 / 3) * (ctrl.y - current.y))
            ctrl2 = fitz.Point(end.x + (2 / 3) * (ctrl.x - end.x), end.y + (2 / 3) * (ctrl.y - end.y))
            shape.draw_bezier(current, ctrl1, ctrl2, end)
            current = end

    dashes = "[4 3] 0" if style.dash == "dashed" else None
    shape.finish(color=style.color, width=style.width, dashes=dashes, closePath=False)
    shape.commit()


def text_value(entity: DXFGraphic) -> str:
    if entity.dxftype() == "MTEXT":
        return entity.plain_text()
    return str(getattr(entity.dxf, "text", ""))


def iter_text_entities(entities: Iterable[DXFGraphic]) -> Iterable[DXFGraphic]:
    for entity in entities:
        if entity.dxftype() in {"TEXT", "MTEXT"} and text_value(entity).strip():
            yield entity


def collect_bounds(entities: Iterable[DXFGraphic]) -> Bounds:
    bounds = Bounds()
    for entity in entities:
        for path in iter_entity_paths(entity):
            for x, y in path:
                bounds.add_point(x, y)
        if entity.dxftype() in {"TEXT", "MTEXT"}:
            insert = entity.dxf.insert
            bounds.add_point(float(insert.x), float(insert.y))
    return bounds


def path_length(path: list[tuple[float, float]]) -> float:
    return sum(math.dist(start, end) for start, end in zip(path, path[1:]))


def is_total_excluded_layer(layer: str) -> bool:
    layer_lower = layer.lower()
    return layer_lower == "0" or "board" in layer_lower or "text" in layer_lower


def collect_stats(entities: Iterable[DXFGraphic]) -> ConversionStats:
    layer_lengths: dict[str, float] = {}
    for entity in entities:
        layer = str(entity.dxf.layer or "0")
        for path in iter_entity_paths(entity):
            layer_lengths[layer] = layer_lengths.get(layer, 0) + path_length(path)

    total_cut_length = sum(length for layer, length in layer_lengths.items() if not is_total_excluded_layer(layer))
    return ConversionStats(layer_lengths=layer_lengths, total_cut_length=total_cut_length)


def convert_point(x: float, y: float, bounds: Bounds, scale: float) -> fitz.Point:
    page_x = PAGE_MARGIN + (x - bounds.min_x) * scale
    page_y = PAGE_HEIGHT - PAGE_MARGIN - (y - bounds.min_y) * scale
    return fitz.Point(page_x, page_y)


def add_stats_page(pdf: fitz.Document, stats: ConversionStats) -> None:
    page = pdf.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = PAGE_MARGIN
    page.insert_text(fitz.Point(PAGE_MARGIN, y), "DXF length summary", fontsize=18, color=(0, 0, 0))
    y += 30
    page.insert_text(
        fitz.Point(PAGE_MARGIN, y),
        "Total length excluding layers containing board/text and layer 0: "
        f"{stats.total_cut_length:.2f}",
        fontsize=11,
        color=(0, 0, 0),
    )
    y += 28
    page.insert_text(fitz.Point(PAGE_MARGIN, y), "Layer", fontsize=10, color=(0, 0, 0))
    page.insert_text(fitz.Point(360, y), "Length", fontsize=10, color=(0, 0, 0))
    y += 16
    for layer, length in sorted(stats.layer_lengths.items(), key=lambda item: item[0].lower()):
        if y > PAGE_HEIGHT - PAGE_MARGIN:
            page = pdf.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = PAGE_MARGIN
        page.insert_text(fitz.Point(PAGE_MARGIN, y), layer[:55], fontsize=9, color=(0, 0, 0))
        page.insert_text(fitz.Point(360, y), f"{length:.2f}", fontsize=9, color=(0, 0, 0))
        y += 14


def convert_dxf_to_pdf(input_path: Path, output_path: Path, raw_layer_styles: str | None = None) -> None:
    try:
        doc = ezdxf.readfile(input_path)
    except ezdxf.DXFError as exc:
        raise ValueError("Could not read DXF file") from exc

    modelspace = list(doc.modelspace())
    bounds = collect_bounds(modelspace)
    if bounds.is_empty:
        raise ValueError("DXF file does not contain supported drawable entities")

    scale = min((PAGE_WIDTH - PAGE_MARGIN * 2) / bounds.width, (PAGE_HEIGHT - PAGE_MARGIN * 2) / bounds.height)
    pdf = fitz.open()
    page = pdf.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    layer_styles = parse_layer_styles(raw_layer_styles)
    stats = collect_stats(modelspace)

    for entity in modelspace:
        style = entity_style(entity, layer_styles)
        draw_entity_path(page, entity, bounds, scale, style)

    for entity in iter_text_entities(modelspace):
        style = entity_style(entity, layer_styles)
        insert = entity.dxf.insert
        point = convert_point(float(insert.x), float(insert.y), bounds, scale)
        size = max(float(getattr(entity.dxf, "height", 2.5)) * scale, 5)
        page.insert_text(point, text_value(entity), fontsize=size, color=style.color, rotate=int(getattr(entity.dxf, "rotation", 0) or 0))

    add_stats_page(pdf, stats)
    pdf.save(output_path)
    pdf.close()


def versioned_conversion_paths(filename: str) -> tuple[Path, Path]:
    safe_name = Path(filename).name
    stem = Path(safe_name).stem or "drawing"
    folder = STORAGE_DIR / stem
    folder.mkdir(parents=True, exist_ok=True)

    version = 1
    while True:
        version_dir = folder / f"v{version:03d}"
        if not version_dir.exists():
            version_dir.mkdir()
            return version_dir / safe_name, version_dir / f"{stem}.pdf"
        version += 1


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "default_styles": DEFAULT_LAYER_STYLES})


@app.post("/convert")
async def convert(file: UploadFile = File(...), layer_styles: str | None = Form(None)) -> FileResponse:
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Upload a .dxf file")

    input_path, output_path = versioned_conversion_paths(file.filename)

    try:
        input_path.write_bytes(await file.read())
        convert_dxf_to_pdf(input_path, output_path, layer_styles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Conversion failed") from exc

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=output_path.name,
    )
