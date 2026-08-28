"""Rasterise résumé pages for preview.

The panel shows the document rather than offering only a download, and it does
so as **images**. An inline PDF would be the obvious route and is the wrong one:
the file was uploaded by a stranger, PDF viewers execute JavaScript, and
rendering one on the panel's own origin is cross-site scripting with an HR
session attached. A PNG executes nothing.

Rendering server-side also means the concealed-text overlay can be drawn from
the same geometry the integrity check already produced.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

# 144 dpi: legible on a high-density screen without turning a three-page résumé
# into three megabytes.
RENDER_DPI = 144
MAX_PAGES = 20


class PageOutOfRangeError(IndexError):
    """The requested page does not exist in this document."""


def page_count(path: Path) -> int:
    document = pymupdf.open(path)  # type: ignore[no-untyped-call]
    try:
        return min(int(document.page_count), MAX_PAGES)
    finally:
        document.close()  # type: ignore[no-untyped-call]


def render_page(path: Path, number: int) -> bytes:
    """Return one page as PNG. `number` is 1-based, as a reader would count."""
    document = pymupdf.open(path)  # type: ignore[no-untyped-call]
    try:
        if number < 1 or number > min(document.page_count, MAX_PAGES):
            raise PageOutOfRangeError(f"Page {number} is not in this document.")
        page = document[number - 1]
        pixmap = page.get_pixmap(dpi=RENDER_DPI)
        data: bytes = pixmap.tobytes("png")  # type: ignore[no-untyped-call]
        return data
    finally:
        document.close()  # type: ignore[no-untyped-call]
