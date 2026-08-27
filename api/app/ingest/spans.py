"""Page geometry and text spans, read from PyMuPDF's low-level trace.

`get_texttrace()` is used rather than `get_text("dict")` because it is the only
view that exposes the drawing sequence number, the text render mode and a float
opacity. Without the sequence number there is no way to tell whether a filled
rectangle was painted over a piece of text or under it, and covering text with
an opaque box is one of the ways a résumé hides instructions from a human reader.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

RGB = tuple[float, float, float]
Box = tuple[float, float, float, float]

WHITE: RGB = (1.0, 1.0, 1.0)
INVISIBLE_RENDER_MODE = 3


@dataclass(frozen=True)
class Span:
    """One run of text with everything needed to decide whether a human sees it."""

    text: str
    size: float
    color: RGB
    opacity: float
    render_mode: int
    bbox: Box
    seqno: int
    page_number: int


@dataclass(frozen=True)
class Fill:
    """A filled shape. Either the background a span sits on, or a lid over it."""

    color: RGB
    opacity: float
    bbox: Box
    seqno: int


@dataclass(frozen=True)
class Page:
    number: int
    mediabox: Box
    spans: tuple[Span, ...]
    fills: tuple[Fill, ...]


# Two baselines closer than this belong to the same line.
_SAME_LINE_TOLERANCE = 0.5


def text_from_chars(chars: object) -> str:
    """Rebuild a span's text, restoring the line breaks the trace drops.

    `get_texttrace()` returns a flat character stream, so a fourteen-line résumé
    arrives as one span and naive concatenation yields "Ada LovelaceSenior
    Backend Engineer". Baseline changes are the only record of where the lines
    were, so they are what the breaks are rebuilt from. Spaces are left alone:
    they are already present as real characters, and inserting more from
    horizontal gaps would corrupt correctly-spaced text.
    """
    if not isinstance(chars, (tuple, list)):
        return ""
    pieces: list[str] = []
    previous_baseline: float | None = None
    for char in chars:
        code, _glyph, origin, _bbox = char
        baseline = float(origin[1])
        if (
            previous_baseline is not None
            and abs(baseline - previous_baseline) > _SAME_LINE_TOLERANCE
        ):
            pieces.append("\n")
        pieces.append(chr(int(code)))
        previous_baseline = baseline
    return "".join(pieces)


def _as_rgb(value: object) -> RGB | None:
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    return None


def read_page(page: pymupdf.Page, number: int) -> Page:
    spans: list[Span] = []
    for raw in page.get_texttrace():  # type: ignore[no-untyped-call]
        text = text_from_chars(raw.get("chars"))
        if not text.strip():
            continue
        text_color: RGB = _as_rgb(raw.get("color")) or (0.0, 0.0, 0.0)
        spans.append(
            Span(
                text=text,
                size=float(raw.get("size", 0.0)),
                color=text_color,
                opacity=float(raw.get("opacity", 1.0)),
                render_mode=int(raw.get("type", 0)),
                bbox=tuple(float(v) for v in raw["bbox"]),  # type: ignore[arg-type]
                seqno=int(raw.get("seqno", 0)),
                page_number=number,
            )
        )

    fills: list[Fill] = []
    for drawing in page.get_drawings():
        fill_color = _as_rgb(drawing.get("fill"))
        if fill_color is None:
            continue  # Stroke-only shape: it does not paint a background.
        fills.append(
            Fill(
                color=fill_color,
                opacity=float(drawing.get("fill_opacity") or 1.0),
                bbox=tuple(float(v) for v in drawing["rect"]),  # type: ignore[arg-type]
                seqno=int(drawing.get("seqno", 0)),
            )
        )

    box = page.mediabox
    return Page(
        number=number,
        mediabox=(float(box.x0), float(box.y0), float(box.x1), float(box.y1)),
        spans=tuple(spans),
        fills=tuple(fills),
    )


def read_document(document: pymupdf.Document) -> list[Page]:
    # Indexed rather than iterated: pymupdf.Document is not typed as an iterable.
    return [read_page(document[index], index + 1) for index in range(document.page_count)]


def contains(outer: Box, inner: Box) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def overlap_ratio(box: Box, region: Box) -> float:
    """How much of `box` falls inside `region`, from 0.0 to 1.0."""
    width = min(box[2], region[2]) - max(box[0], region[0])
    height = min(box[3], region[3]) - max(box[1], region[1])
    if width <= 0 or height <= 0:
        return 0.0
    area = (box[2] - box[0]) * (box[3] - box[1])
    return 0.0 if area <= 0 else (width * height) / area
