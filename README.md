# DXF to PDF / SVG Converter

Local web service for converting DXF drawings to PDF (with scale preservation and layer support) and SVG (for Adobe Illustrator).

## Features

- **Scale preservation** — PDF page size matches the DXF drawing dimensions, not forced to A4
- **PDF layers (OCG)** — DXF layers exported as Optional Content Groups, visible in Adobe Acrobat and other PDF viewers
- **SVG with layers** — DXF layers exported as Inkscape-compatible `<g>` groups, recognized as layers by Adobe Illustrator
- **Length summary** — optional per-layer and total length report (in mm) on the same page as the drawing
- **Layer style rules** — customizable color, width, dash style per layer via the web UI
- **Include in total** — per-rule toggle to control which layers contribute to the summary total
- **Multi-language UI** — English, Russian, Spanish, Chinese
- **Light/dark theme** — toggle in the browser
- **Settings persistence** — rules and preferences saved in `localStorage`
- **Versioned output** — each conversion saved in `converted_files/<name>/v001/`, `v002/`, ...

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser.

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Docker (optional)

```bash
docker build -t dxf-converter .
docker run -p 8000:8000 dxf-converter
```

## Usage

1. Open the web interface at http://127.0.0.1:8000
2. Drag and drop a `.dxf` file or click the upload area
3. Conversion starts automatically
4. Preview the PDF in the browser
5. Download PDF or SVG

### Output modes

| Mode | Description |
|------|-------------|
| **PDF only** | Drawing only |
| **PDF + summary** | Drawing with compact length summary on the same page |

### SVG for Illustrator

Click **Download SVG (Illustrator)** to get an SVG file where each DXF layer becomes a separate `<g>` group with Inkscape layer attributes. Adobe Illustrator CC 23.0+ opens these as individual layers.

### Layer style rules

Open **Layer styles** settings to customize:

- **Match** — layer name substring (case-insensitive)
- **Color** — stroke color
- **Width** — stroke width in pt
- **Line** — solid or dashed
- **Include in total** — whether this layer is counted in the summary total

Click **Save settings** to persist rules in the browser.

## Architecture

```
app/
  main.py            FastAPI routes (/convert, /convert-svg)
  converter.py       DXF → PDF conversion with OCG layers
  svg_export.py      DXF → SVG conversion with layer groups
  geometry.py        Bounds calculation, coordinate conversion
  stats.py           Length statistics, summary drawing
  layer_styles.py    Rule parsing, default styles, ACAD colors
  constants.py       Page dimensions, unit conversion tables
  templates/
    index.html       Web UI with i18n (EN/RU/ES/ZH)
  static/
    style.css        Light/dark theme styles
```

## Supported DXF entities

| Entity | Description |
|--------|-------------|
| `LINE` | Straight line |
| `ARC` | Arc segment |
| `CIRCLE` | Circle |
| `LWPOLYLINE` | Lightweight polyline |
| `POLYLINE` | Polyline |
| `TEXT` | Single-line text |
| `MTEXT` | Multi-line text |

## DXF units

The converter reads `$INSUNITS` from the DXF header:

| Code | Unit | Scale |
|------|------|-------|
| 0 | Unitless | 1 (mm assumed) |
| 1 | Inches | 25.4 |
| 4 | Millimeters | 1 |
| 5 | Centimeters | 10 |
| 6 | Meters | 1000 |

## Dependencies

- **FastAPI** — web framework
- **uvicorn** — ASGI server
- **ezdxf** — DXF parsing
- **PyMuPDF (fitz)** — PDF generation with OCG layers
- **Jinja2** — HTML templating
- **python-multipart** — file upload support

## License

MIT
