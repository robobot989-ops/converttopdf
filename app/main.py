from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import ezdxf

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .converter import convert_dxf_to_pdf
from .stats import stats_to_dict
from .svg_export import convert_dxf_to_svg
from .layer_styles import DEFAULT_LAYER_STYLES
from .thumbnails import get_or_create_thumbnail


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ROOT_DIR.parent
STORAGE_DIR = PROJECT_DIR / "converted_files"
THUMB_DIR = PROJECT_DIR / "thumbnails"

app = FastAPI(title="DXF to PDF Converter")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
app.mount("/thumbs", StaticFiles(directory=THUMB_DIR), name="thumbs")
templates = Jinja2Templates(directory=ROOT_DIR / "templates")


def versioned_conversion_paths(filename: str) -> tuple[Path, Path, Path, Path]:
    safe_name = Path(filename).name
    stem = Path(safe_name).stem or "drawing"
    folder = STORAGE_DIR / stem
    folder.mkdir(parents=True, exist_ok=True)

    version = 1
    while True:
        version_dir = folder / f"v{version:03d}"
        if not version_dir.exists():
            version_dir.mkdir()
            return (
                version_dir / safe_name,
                version_dir / f"{stem}.pdf",
                version_dir / f"{stem}.svg",
                version_dir / f"{stem}_summary.json",
            )
        version += 1


def list_conversions() -> list[dict]:
    if not STORAGE_DIR.exists():
        return []
    items = []
    for drawing_dir in STORAGE_DIR.iterdir():
        if not drawing_dir.is_dir():
            continue
        for version_dir in sorted(drawing_dir.iterdir(), reverse=True):
            pdf = version_dir / f"{drawing_dir.name}.pdf"
            svg = version_dir / f"{drawing_dir.name}.svg"
            summary_file = version_dir / f"{drawing_dir.name}_summary.json"
            if pdf.exists():
                stat = pdf.stat()
                thumb = get_or_create_thumbnail(pdf, THUMB_DIR)
                summary = None
                if summary_file.exists():
                    try:
                        summary = json.loads(summary_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        summary = None
                items.append({
                    "name": drawing_dir.name,
                    "version": version_dir.name,
                    "pdf": f"/archive/{drawing_dir.name}/{version_dir.name}/{pdf.name}",
                    "svg": f"/archive/{drawing_dir.name}/{version_dir.name}/{svg.name}" if svg.exists() else None,
                    "thumb": f"/thumbs/{thumb.name}" if thumb else None,
                    "summary": summary,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "delete_url": f"/api/archive/{drawing_dir.name}/{version_dir.name}",
                })
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items


@app.get("/archive/{drawing}/{version}/{filename}")
async def serve_archive(drawing: str, version: str, filename: str) -> FileResponse:
    path = STORAGE_DIR / drawing / version / filename
    if not path.exists() or not path.is_relative_to(STORAGE_DIR):
        raise HTTPException(status_code=404, detail="Not found")
    media_type = "application/pdf" if filename.endswith(".pdf") else "image/svg+xml"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/conversions")
async def api_conversions():
    return {"items": list_conversions()}


@app.delete("/api/archive/{drawing}/{version}")
async def delete_archive(drawing: str, version: str):
    version_dir = STORAGE_DIR / drawing / version
    if not version_dir.exists() or not version_dir.is_relative_to(STORAGE_DIR):
        raise HTTPException(status_code=404, detail="Not found")
    shutil.rmtree(version_dir)
    parent = STORAGE_DIR / drawing
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
    return {"ok": True}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("settings.html", {"request": request, "default_styles": DEFAULT_LAYER_STYLES})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "default_styles": DEFAULT_LAYER_STYLES})


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    layer_styles: str | None = Form(None),
    include_summary: bool = Form(False),
):
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Upload a .dxf file")

    input_path, output_pdf, output_svg, output_summary = versioned_conversion_paths(file.filename)

    try:
        input_path.write_bytes(await file.read())
        try:
            doc = ezdxf.readfile(input_path)
        except ezdxf.DXFError as exc:
            raise ValueError("Could not read DXF file") from exc
        stats, mm_per_unit = convert_dxf_to_pdf(input_path, output_pdf, layer_styles, include_summary=include_summary, doc=doc)
        convert_dxf_to_svg(input_path, output_svg, layer_styles, doc=doc)
        summary_data = stats_to_dict(stats, mm_per_unit)
        output_summary.write_text(json.dumps(summary_data, ensure_ascii=False), encoding="utf-8")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Conversion failed") from exc

    drawing_name = input_path.parent.parent.name
    version_name = input_path.parent.name
    return JSONResponse({
        "pdf_url": f"/archive/{drawing_name}/{version_name}/{output_pdf.name}",
        "summary": summary_data,
    })


@app.post("/convert-svg")
async def convert_svg(
    file: UploadFile = File(...),
    layer_styles: str | None = Form(None),
) -> FileResponse:
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Upload a .dxf file")

    input_path, _, output_svg, _ = versioned_conversion_paths(file.filename)

    try:
        input_path.write_bytes(await file.read())
        convert_dxf_to_svg(input_path, output_svg, layer_styles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Conversion failed") from exc

    return FileResponse(
        output_svg,
        media_type="image/svg+xml",
        filename=output_svg.name,
    )
