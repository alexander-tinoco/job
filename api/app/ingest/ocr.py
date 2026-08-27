"""Tesseract fallback for résumés that arrive as scans.

A scanned page has no text layer, so there are no spans, no colours and no font
sizes. **Layer 1 of the anti-injection design does not exist for these files**
(plan §6): nothing can be checked against what a human sees, because the page is
a picture. Such applications are marked for manual review rather than quietly
evaluated as though they had been verified.

Tesseract is a system binary, not a Python package. When it is missing the file
is still accepted and still flagged — the pipeline degrades, it does not break.
"""

from __future__ import annotations

import shutil

import pymupdf

# Fewer characters than this *per page* means there is no usable text layer.
# Scaled by page count rather than applied to the whole document: a three-page
# scan carrying a short text watermark would otherwise skip OCR entirely.
MIN_TEXT_LAYER_CHARS_PER_PAGE = 50


class OcrUnavailableError(RuntimeError):
    """Tesseract is not installed on this machine."""


def is_available() -> bool:
    return shutil.which("tesseract") is not None


def needs_ocr(document: pymupdf.Document) -> bool:
    extracted = "".join(
        str(document[index].get_text()).strip()  # type: ignore[no-untyped-call]
        for index in range(document.page_count)
    )
    budget = MIN_TEXT_LAYER_CHARS_PER_PAGE * max(1, int(document.page_count))
    return len(extracted) < budget


def extract_with_ocr(document: pymupdf.Document, language: str = "spa+eng") -> str:
    """Run Tesseract over every page and return the recognised text."""
    if not is_available():
        raise OcrUnavailableError(
            "Tesseract is not installed. Install it with: "
            "apt install tesseract-ocr tesseract-ocr-spa"
        )

    parts: list[str] = []
    for index in range(document.page_count):
        page = document[index]
        textpage = page.get_textpage_ocr(language=language, full=True)  # type: ignore[no-untyped-call]
        parts.append(str(page.get_text(textpage=textpage)))  # type: ignore[no-untyped-call]
    return "\n".join(parts)
