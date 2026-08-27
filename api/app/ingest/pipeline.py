"""Turn a stored PDF into sanitized text plus an integrity report.

Deterministic from end to end: no model is called here, and none of it costs
anything to run. That is the point — everything an algorithm can settle is
settled before the single AI call of the pipeline (plan §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf

from app.ingest import ocr
from app.ingest.hidden import HiddenSpan, split_visible
from app.ingest.patterns import find_patterns, strip_delimiter_spoofing
from app.ingest.spans import read_document

# Hidden text long enough to carry an instruction. Below this it is usually a
# stray glyph or a rendering artefact, not an attack.
TAMPERING_CHAR_THRESHOLD = 25


class ExtractionError(Exception):
    """The file could not be read as a PDF at all."""


@dataclass(frozen=True)
class ExtractionResult:
    visible_text: str
    total_text: str
    page_count: int
    hidden_spans: list[HiddenSpan] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)
    used_ocr: bool = False
    needs_manual_review: bool = False
    review_reason: str = ""

    @property
    def hidden_char_count(self) -> int:
        return sum(len(span.text.strip()) for span in self.hidden_spans)


def extract(path: Path) -> ExtractionResult:
    try:
        document = pymupdf.open(path)  # type: ignore[no-untyped-call]
    except Exception as exc:  # pymupdf raises a broad family for malformed files
        raise ExtractionError(f"Could not open the PDF: {exc}") from exc

    try:
        if ocr.needs_ocr(document):
            return _extract_scanned(document)
        return _extract_digital(document)
    finally:
        document.close()  # type: ignore[no-untyped-call]


def _extract_digital(document: pymupdf.Document) -> ExtractionResult:
    pages = read_document(document)
    visible, total, hidden = split_visible(pages)
    sanitized = strip_delimiter_spoofing(visible)

    return ExtractionResult(
        visible_text=sanitized,
        total_text=total,
        page_count=document.page_count,
        hidden_spans=hidden,
        # Run over the whole document: a pattern buried in hidden text is the
        # strongest signal there is, and it would be missed by scanning only
        # what stays visible.
        matched_patterns=find_patterns(total),
        needs_manual_review=False,
    )


def _extract_scanned(document: pymupdf.Document) -> ExtractionResult:
    """A scan has no text layer, so layer 1 cannot protect it (plan §6)."""
    base = ExtractionResult(
        visible_text="",
        total_text="",
        page_count=document.page_count,
        used_ocr=True,
        needs_manual_review=True,
        review_reason=(
            "Scanned résumé: there is no text layer, so hidden text cannot be detected. "
            "Read the original before trusting the evaluation."
        ),
    )

    try:
        text = ocr.extract_with_ocr(document)
    except ocr.OcrUnavailableError as exc:
        return replace(base, review_reason=f"{base.review_reason} OCR unavailable: {exc}")

    return replace(
        base,
        visible_text=strip_delimiter_spoofing(text),
        total_text=text,
        matched_patterns=find_patterns(text),
    )
