# DXF to PDF Converter

Local web service for converting a single DXF drawing into a vector PDF.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and choose a `.dxf` file. Conversion starts automatically and the PDF preview appears in the browser.

The generated PDF keeps the drawing scale instead of forcing the content into A4. The page size is derived from the DXF bounds and the file units.

PDF output modes:

- `PDF only`: drawing only.
- `PDF + summary`: drawing and compact length summary on the same PDF page.

DXF layers with drawable content are exported as PDF optional content groups. Empty DXF layers are not exported. Summary lengths are shown in millimeters, including whether each layer is counted in the total.

Adobe Acrobat and other PDF viewers can display these optional content groups as PDF layers. Adobe Illustrator may still import a standard layered PDF as a single Illustrator layer because Illustrator layers and PDF optional content groups are different mechanisms.

## UI Features

- Automatic conversion after file selection
- PDF preview before download
- Light/dark theme switcher
- Editable layer style rules in the web interface
- Saved DXF/PDF conversion versions in `converted_files/`
- PDF length summary by layer and total length excluding `board`, `text`, and `0` layers

Default layer rules:

- `cut`: red, 1 pt, solid
- `Board`: black, 0.5 pt, dashed
- `big`: green, 1 pt, solid
- `ric`: blue, 1 pt, solid
- `prf`: green, 1 pt, dashed
- `text`: gray, 0.5 pt, solid

## Supported DXF Entities

- `LINE`
- `ARC`
- `CIRCLE`
- `LWPOLYLINE`
- `POLYLINE`
- `TEXT`
- `MTEXT`

The service uses only free Python dependencies: FastAPI, ezdxf, and PyMuPDF.
