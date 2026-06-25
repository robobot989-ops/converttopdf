from __future__ import annotations

import ezdxf
import ezdxf.path
import fitz
from pathlib import Path

from .constants import DXF_INSUNITS_TO_MM, PAGE_MARGIN, POINTS_PER_MM
from .geometry import Bounds, collect_bounds, convert_point, iter_text_entities, text_value
from .layer_styles import LayerStyle, entity_style, layer_include_in_total, parse_layer_styles
from .stats import ConversionStats, collect_stats, draw_summary, summary_height


def dxf_mm_per_unit(doc: ezdxf.EzdxfDocument) -> float:
    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    return DXF_INSUNITS_TO_MM.get(insunits, 1.0)


def unit_scale_to_points(doc: ezdxf.EzdxfDocument) -> float:
    return dxf_mm_per_unit(doc) * POINTS_PER_MM


def ocg_for_layer(pdf: fitz.Document, ocgs: dict[str, int], layer: str) -> int:
    layer_name = layer.strip() or "0"
    if layer_name not in ocgs:
        ocgs[layer_name] = pdf.add_ocg(layer_name)
    return ocgs[layer_name]


def draw_entity_path(
    page: fitz.Page,
    entity: ezdxf.entities.DXFGraphic,
    bounds: Bounds,
    scale: float,
    page_height: float,
    style: LayerStyle,
    ocg: int,
) -> None:
    entity_type = entity.dxftype()
    if entity_type not in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
        return

    try:
        path = ezdxf.path.make_path(entity)
    except TypeError:
        return

    shape = page.new_shape()
    current = convert_point(float(path.start.x), float(path.start.y), bounds, scale, page_height)
    for command in path:
        command_name = command.__class__.__name__
        if command_name == "LineTo":
            end = convert_point(float(command.end.x), float(command.end.y), bounds, scale, page_height)
            shape.draw_line(current, end)
            current = end
        elif command_name == "Curve4To":
            ctrl1 = convert_point(float(command.ctrl1.x), float(command.ctrl1.y), bounds, scale, page_height)
            ctrl2 = convert_point(float(command.ctrl2.x), float(command.ctrl2.y), bounds, scale, page_height)
            end = convert_point(float(command.end.x), float(command.end.y), bounds, scale, page_height)
            shape.draw_bezier(current, ctrl1, ctrl2, end)
            current = end
        elif command_name == "Curve3To":
            ctrl = convert_point(float(command.ctrl.x), float(command.ctrl.y), bounds, scale, page_height)
            end = convert_point(float(command.end.x), float(command.end.y), bounds, scale, page_height)
            ctrl1 = fitz.Point(current.x + (2 / 3) * (ctrl.x - current.x), current.y + (2 / 3) * (ctrl.y - current.y))
            ctrl2 = fitz.Point(end.x + (2 / 3) * (ctrl.x - end.x), end.y + (2 / 3) * (ctrl.y - end.y))
            shape.draw_bezier(current, ctrl1, ctrl2, end)
            current = end

    dashes = "[4 3] 0" if style.dash == "dashed" else None
    shape.finish(color=style.color, width=style.width, dashes=dashes, closePath=False, oc=ocg)
    shape.commit()


def convert_dxf_to_pdf(
    input_path: Path,
    output_path: Path,
    raw_layer_styles: str | None = None,
    include_summary: bool = False,
    doc: ezdxf.EzdxfDocument | None = None,
) -> tuple[ConversionStats, float]:
    if doc is None:
        try:
            doc = ezdxf.readfile(input_path)
        except ezdxf.DXFError as exc:
            raise ValueError("Could not read DXF file") from exc

    modelspace = list(doc.modelspace())
    bounds = collect_bounds(modelspace)
    if bounds.is_empty:
        raise ValueError("DXF file does not contain supported drawable entities")

    mm_per_unit = dxf_mm_per_unit(doc)
    scale = mm_per_unit * POINTS_PER_MM
    layer_styles = parse_layer_styles(raw_layer_styles)
    stats = collect_stats(modelspace, lambda layer: layer_include_in_total(layer, layer_styles))
    report_height = summary_height(stats) if include_summary else 0
    page_width = bounds.width * scale + PAGE_MARGIN * 2
    page_height = bounds.height * scale + PAGE_MARGIN * 2 + report_height
    pdf = fitz.open()
    page = pdf.new_page(width=page_width, height=page_height)
    ocgs: dict[str, int] = {}

    if include_summary:
        draw_summary(page, stats, mm_per_unit)

    for entity in modelspace:
        style = entity_style(entity, layer_styles)
        ocg = ocg_for_layer(pdf, ocgs, str(entity.dxf.layer or "0"))
        draw_entity_path(page, entity, bounds, scale, page_height, style, ocg)

    for entity in iter_text_entities(modelspace):
        style = entity_style(entity, layer_styles)
        ocg = ocg_for_layer(pdf, ocgs, str(entity.dxf.layer or "0"))
        insert = entity.dxf.insert
        point = convert_point(float(insert.x), float(insert.y), bounds, scale, page_height)
        size = max(float(getattr(entity.dxf, "height", 2.5)) * scale, 5)
        page.insert_text(
            point,
            text_value(entity),
            fontsize=size,
            color=style.color,
            rotate=int(getattr(entity.dxf, "rotation", 0) or 0),
            oc=ocg,
        )

    pdf.save(output_path)
    pdf.close()
    return stats, mm_per_unit
