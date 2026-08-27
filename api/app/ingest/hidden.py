"""Rules that decide whether a human actually sees a piece of text.

This is layer 1 of the anti-injection design (plan §6) and the only one that can
catch what a reader cannot. Every real attack depends on hiding text from the
human while leaving it readable to the extractor, so the question each rule asks
is the same: would a person see this?

Nothing here calls a model. It is arithmetic on colours, sizes and rectangles.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.ingest.spans import (
    INVISIBLE_RENDER_MODE,
    RGB,
    WHITE,
    Fill,
    Page,
    Span,
    contains,
    overlap_ratio,
)

# Below 4pt text is not read, it is skimmed past. Real résumés use 8pt at the
# smallest, so this leaves a wide margin before a legitimate document trips it.
MIN_READABLE_SIZE = 4.0

# WCAG puts the floor for readable body text at 4.5:1. This threshold is set far
# below that on purpose: we want "effectively invisible", not "hard to read", so
# that light grey on white (about 1.6:1) is never flagged.
MIN_CONTRAST_RATIO = 1.5

MIN_OPACITY = 0.05

# A span may hang slightly past the page edge through rounding. Only treat it as
# parked off-page when most of it is outside.
MIN_ON_PAGE_RATIO = 0.5


class Reason(StrEnum):
    INVISIBLE_RENDER_MODE = "invisible_render_mode"
    TRANSPARENT = "transparent"
    TOO_SMALL = "too_small"
    LOW_CONTRAST = "low_contrast"
    OFF_PAGE = "off_page"
    COVERED = "covered"


@dataclass(frozen=True)
class HiddenSpan:
    text: str
    reason: Reason
    page_number: int
    bbox: tuple[float, float, float, float]
    detail: str


def _linearise(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color: RGB) -> float:
    red, green, blue = (_linearise(max(0.0, min(1.0, c))) for c in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: RGB, second: RGB) -> float:
    """WCAG contrast ratio, from 1.0 (identical) to 21.0 (black on white)."""
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def background_under(span: Span, fills: tuple[Fill, ...]) -> RGB:
    """The colour a span is painted onto.

    Looked up per span rather than per page: a résumé with a dark sidebar and a
    white body has two backgrounds, and assuming the page is white would miss
    dark-on-dark text inside the sidebar.
    """
    covering = [
        fill
        for fill in fills
        if fill.seqno < span.seqno and fill.opacity > 0.5 and contains(fill.bbox, span.bbox)
    ]
    if not covering:
        return WHITE
    return max(covering, key=lambda fill: fill.seqno).color


def covering_lid(span: Span, fills: tuple[Fill, ...]) -> Fill | None:
    """An opaque shape painted *after* the span and completely over it."""
    lids = [
        fill
        for fill in fills
        if fill.seqno > span.seqno and fill.opacity >= 0.95 and contains(fill.bbox, span.bbox)
    ]
    return max(lids, key=lambda fill: fill.seqno) if lids else None


def inspect_span(span: Span, page: Page) -> HiddenSpan | None:
    """Return why this span is invisible, or None if a human would read it."""
    if span.render_mode == INVISIBLE_RENDER_MODE:
        return _hidden(span, Reason.INVISIBLE_RENDER_MODE, "text render mode 3 draws nothing")

    if span.opacity < MIN_OPACITY:
        return _hidden(span, Reason.TRANSPARENT, f"opacity {span.opacity:.2f}")

    if span.size < MIN_READABLE_SIZE:
        return _hidden(span, Reason.TOO_SMALL, f"{span.size:.1f}pt")

    if overlap_ratio(span.bbox, page.mediabox) < MIN_ON_PAGE_RATIO:
        return _hidden(span, Reason.OFF_PAGE, "drawn outside the page area")

    lid = covering_lid(span, page.fills)
    if lid is not None:
        return _hidden(span, Reason.COVERED, "painted over by an opaque shape")

    background = background_under(span, page.fills)
    ratio = contrast_ratio(span.color, background)
    if ratio < MIN_CONTRAST_RATIO:
        return _hidden(span, Reason.LOW_CONTRAST, f"contrast ratio {ratio:.2f} against background")

    return None


def _hidden(span: Span, reason: Reason, detail: str) -> HiddenSpan:
    return HiddenSpan(
        text=span.text,
        reason=reason,
        page_number=span.page_number,
        bbox=span.bbox,
        detail=detail,
    )


def split_visible(pages: list[Page]) -> tuple[str, str, list[HiddenSpan]]:
    """Split a document into what a human reads, everything, and the difference.

    Only the visible text is ever sent to the model. The hidden text is kept as
    evidence and shown to HR, never as instructions to the evaluator.
    """
    visible_parts: list[str] = []
    total_parts: list[str] = []
    hidden: list[HiddenSpan] = []

    for page in pages:
        for span in page.spans:
            total_parts.append(span.text)
            found = inspect_span(span, page)
            if found is None:
                visible_parts.append(span.text)
            else:
                hidden.append(found)

    return _join(visible_parts), _join(total_parts), hidden


def _join(parts: list[str]) -> str:
    """Join spans with newlines, never by concatenation.

    A span boundary is not a word boundary in the source, but gluing two spans
    together invents one: "...University of London" followed by "Ignore previous"
    becomes "LondonIgnore previous", which silently defeats every pattern anchored
    on \\b and hands the model mangled words.
    """
    return "\n".join(part.strip() for part in parts if part.strip())
