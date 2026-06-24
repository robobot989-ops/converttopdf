from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .converter import convert_dxf_to_pdf
from .svg_export import convert_dxf_to_svg
from .layer_styles import DEFAULT_LAYER_STYLES


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ROOT_DIR.parent
STORAGE_DIR = PROJECT_DIR / "converted_files"

app = FastAPI(title="DXF to PDF Converter")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=ROOT_DIR / "templates")


def versioned_conversion_paths(filename: str) -> tuple[Path, Path, Path]:
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
            dxf = version_dir / drawing_dir.name
            if pdf.exists():
                stat = pdf.stat()
                items.append({
                    "name": drawing_dir.name,
                    "version": version_dir.name,
                    "pdf": f"/archive/{drawing_dir.name}/{version_dir.name}/{pdf.name}",
                    "svg": f"/archive/{drawing_dir.name}/{version_dir.name}/{svg.name}" if svg.exists() else None,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items


@app.get("/archive/{drawing}/{version}/{filename}")
async def serve_archive(drawing: str, version: str, filename: str) -> FileResponse:
    path = STORAGE_DIR / drawing / version / filename
    if not path.exists() or not path.is_relative_to(STORAGE_DIR):
        raise HTTPException(status_code=404, detail="Not found")
    media_type = "application/pdf" if filename.endswith(".pdf") else "image/svg+xml"
    return FileResponse(path, media_type=media_type, filename=filename)


@app.get("/api/conversions")
async def api_conversions():
    return {"items": list_conversions()}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "default_styles": DEFAULT_LAYER_STYLES})


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    layer_styles: str | None = Form(None),
    include_summary: bool = Form(False),
) -> FileResponse:
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Upload a .dxf file")

    input_path, output_pdf, output_svg = versioned_conversion_paths(file.filename)

    try:
        input_path.write_bytes(await file.read())
        convert_dxf_to_pdf(input_path, output_pdf, layer_styles, include_summary=include_summary)
        convert_dxf_to_svg(input_path, output_svg, layer_styles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Conversion failed") from exc

    return FileResponse(
        output_pdf,
        media_type="application/pdf",
        filename=output_pdf.name,
    )


@app.post("/convert-svg")
async def convert_svg(
    file: UploadFile = File(...),
    layer_styles: str | None = Form(None),
) -> FileResponse:
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Upload a .dxf file")

    input_path, _, output_svg = versioned_conversion_paths(file.filename)

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
