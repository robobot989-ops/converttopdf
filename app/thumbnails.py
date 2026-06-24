from __future__ import annotations

from pathlib import Path

import fitz


def generate_pdf_thumbnail(pdf_path: Path, thumb_path: Path, max_size: int = 200) -> bool:
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            doc.close()
            return False
        page = doc[0]
        rect = page.rect
        scale = min(max_size / rect.width, max_size / rect.height, 1.0)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix.save(str(thumb_path))
        doc.close()
        return True
    except Exception:
        return False


def get_or_create_thumbnail(pdf_path: Path, thumb_dir: Path, max_size: int = 200) -> Path | None:
    thumb_name = f"{pdf_path.stem}_thumb.jpg"
    thumb_path = thumb_dir / thumb_name
    if thumb_path.exists():
        return thumb_path
    thumb_dir.mkdir(parents=True, exist_ok=True)
    if generate_pdf_thumbnail(pdf_path, thumb_path, max_size):
        return thumb_path
    return None
