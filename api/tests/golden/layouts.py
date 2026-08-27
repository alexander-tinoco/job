"""Ten visually different résumé layouts, rendered with PyMuPDF.

Format is not cosmetic here. The extraction pipeline reads spans, colours and
geometry (plan §4), so a coloured sidebar, a two-column grid and a plain ATS
export exercise genuinely different paths. A model comparison run only on tidy
single-column text would not tell us how the product behaves on what people
actually upload.
"""

from __future__ import annotations

import pymupdf

from tests.golden.candidates import Candidate

RGB = tuple[float, float, float]
BLACK: RGB = (0.0, 0.0, 0.0)
WHITE: RGB = (1.0, 1.0, 1.0)
GREY: RGB = (0.42, 0.42, 0.42)

PAGE = pymupdf.paper_rect("a4")
SERIF = "tiro"
SANS = "helv"
SANS_BOLD = "hebo"


class _Cursor:
    """Writes down a column, wrapping text and starting new pages as needed."""

    def __init__(self, page: pymupdf.Page, left: float, right: float, top: float) -> None:
        self.page = page
        self.left = left
        self.right = right
        self.y = top

    def write(
        self,
        text: str,
        size: float = 9.5,
        color: RGB = BLACK,
        font: str = SANS,
        leading: float = 1.35,
        gap_after: float = 3.0,
    ) -> None:
        width = self.right - self.left
        for line in _wrap(text, width, size):
            self.page.insert_text(
                (self.left, self.y), line, fontsize=size, color=color, fontname=font
            )
            self.y += size * leading
        self.y += gap_after

    def rule(self, color: RGB = GREY, width: float = 0.6) -> None:
        self.page.draw_line(
            pymupdf.Point(self.left, self.y),
            pymupdf.Point(self.right, self.y),
            color=color,
            width=width,
        )
        self.y += 8


def _wrap(text: str, width: float, size: float) -> list[str]:
    """Greedy wrap using the real glyph widths of the font."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pymupdf.get_text_length(candidate, fontname=SANS, fontsize=size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _body(cursor: _Cursor, candidate: Candidate, heading_color: RGB, font: str = SANS) -> None:
    cursor.write("EXPERIENCE", size=10, color=heading_color, font=SANS_BOLD, gap_after=5)
    for title, context, bullets in candidate.experience:
        cursor.write(title, size=9.5, font=SANS_BOLD, gap_after=1)
        cursor.write(context, size=8.5, color=GREY, gap_after=3)
        for bullet in bullets:
            cursor.write(f"•  {bullet}", size=9, font=font, gap_after=2)
        cursor.y += 4
    cursor.write("EDUCATION", size=10, color=heading_color, font=SANS_BOLD, gap_after=5)
    for line in candidate.education:
        cursor.write(line, size=9, gap_after=2)


def _skills(cursor: _Cursor, candidate: Candidate, color: RGB, heading: RGB) -> None:
    cursor.write("SKILLS", size=10, color=heading, font=SANS_BOLD, gap_after=5)
    for skill in candidate.skills:
        cursor.write(f"·  {skill}", size=8.5, color=color, gap_after=2)


def harvard(page: pymupdf.Page, candidate: Candidate) -> None:
    """Classic single column, serif, centred header, black on white."""
    title_width = pymupdf.get_text_length(candidate.name, fontname="tibo", fontsize=18)
    page.insert_text(
        ((PAGE.width - title_width) / 2, 70), candidate.name, fontsize=18, fontname="tibo"
    )
    sub = f"{candidate.headline}  ·  {candidate.location}"
    sub_width = pymupdf.get_text_length(sub, fontname=SERIF, fontsize=9.5)
    page.insert_text(((PAGE.width - sub_width) / 2, 86), sub, fontsize=9.5, fontname=SERIF)

    cursor = _Cursor(page, 70, PAGE.width - 70, 108)
    cursor.rule(BLACK, 0.9)
    cursor.write(candidate.summary, size=9.5, font=SERIF, gap_after=10)
    _body(cursor, candidate, BLACK, font=SERIF)
    cursor.y += 6
    _skills(cursor, candidate, BLACK, BLACK)


def canva_sidebar(page: pymupdf.Page, candidate: Candidate) -> None:
    """Coloured left rail with the contact block and skills, content on the right."""
    rail = pymupdf.Rect(0, 0, 185, PAGE.height)
    page.draw_rect(rail, color=None, fill=candidate.accent)

    left = _Cursor(page, 22, 165, 70)
    left.write(candidate.name, size=16, color=WHITE, font=SANS_BOLD, gap_after=4)
    left.write(candidate.headline, size=9.5, color=WHITE, gap_after=2)
    left.write(candidate.location, size=8.5, color=WHITE, gap_after=16)
    _skills(left, candidate, WHITE, WHITE)

    right = _Cursor(page, 210, PAGE.width - 45, 74)
    right.write(candidate.summary, size=9.5, gap_after=10)
    _body(right, candidate, candidate.accent)


def modern_header(page: pymupdf.Page, candidate: Candidate) -> None:
    """Full-width colour band, then a single column beneath it."""
    page.draw_rect(pymupdf.Rect(0, 0, PAGE.width, 104), color=None, fill=candidate.accent)
    page.insert_text((55, 52), candidate.name, fontsize=20, color=WHITE, fontname=SANS_BOLD)
    page.insert_text((55, 72), candidate.headline, fontsize=10, color=WHITE)
    page.insert_text((55, 88), candidate.location, fontsize=9, color=WHITE)

    cursor = _Cursor(page, 55, PAGE.width - 55, 132)
    cursor.write(candidate.summary, size=9.5, gap_after=10)
    _body(cursor, candidate, candidate.accent)
    cursor.y += 6
    _skills(cursor, candidate, BLACK, candidate.accent)


def minimalist(page: pymupdf.Page, candidate: Candidate) -> None:
    """Generous whitespace, thin rules, grey accents."""
    page.insert_text((80, 96), candidate.name, fontsize=15, fontname=SANS)
    page.insert_text((80, 112), candidate.headline.upper(), fontsize=8, color=GREY)
    page.insert_text((80, 126), candidate.location, fontsize=8, color=GREY)

    cursor = _Cursor(page, 80, PAGE.width - 80, 156)
    cursor.rule(GREY, 0.4)
    cursor.write(candidate.summary, size=9.5, color=(0.2, 0.2, 0.2), gap_after=14)
    _body(cursor, candidate, GREY)
    cursor.y += 8
    _skills(cursor, candidate, (0.2, 0.2, 0.2), GREY)


def academic_dense(page: pymupdf.Page, candidate: Candidate) -> None:
    """Small type, tight leading, the density of a CV rather than a résumé."""
    page.insert_text((50, 58), candidate.name, fontsize=13, fontname="tibo")
    page.insert_text(
        (50, 72), f"{candidate.headline} — {candidate.location}", fontsize=8.5, fontname=SERIF
    )

    cursor = _Cursor(page, 50, PAGE.width - 50, 92)
    cursor.rule(BLACK, 0.5)
    cursor.write(candidate.summary, size=8.5, font=SERIF, leading=1.2, gap_after=8)
    for title, context, bullets in candidate.experience:
        cursor.write(title, size=8.5, font="tibo", leading=1.2, gap_after=1)
        cursor.write(context, size=8, color=GREY, font=SERIF, leading=1.2, gap_after=2)
        for bullet in bullets:
            cursor.write(bullet, size=8.5, font=SERIF, leading=1.2, gap_after=1)
        cursor.y += 3
    cursor.write("EDUCATION", size=9, font="tibo", leading=1.2, gap_after=3)
    for line in candidate.education:
        cursor.write(line, size=8.5, font=SERIF, leading=1.2, gap_after=1)
    cursor.y += 5
    cursor.write("TECHNICAL SKILLS", size=9, font="tibo", leading=1.2, gap_after=3)
    for skill in candidate.skills:
        cursor.write(skill, size=8.5, font=SERIF, leading=1.2, gap_after=1)


def creative_blocks(page: pymupdf.Page, candidate: Candidate) -> None:
    """Coloured section blocks with reversed-out headings."""
    page.draw_rect(pymupdf.Rect(40, 40, PAGE.width - 40, 96), color=None, fill=candidate.accent)
    page.insert_text((56, 68), candidate.name, fontsize=17, color=WHITE, fontname=SANS_BOLD)
    page.insert_text(
        (56, 84), f"{candidate.headline} · {candidate.location}", fontsize=9, color=WHITE
    )

    cursor = _Cursor(page, 56, PAGE.width - 56, 118)
    cursor.write(candidate.summary, size=9.5, gap_after=12)
    block = pymupdf.Rect(40, cursor.y - 12, PAGE.width - 40, cursor.y + 6)
    page.draw_rect(block, color=None, fill=candidate.accent)
    page.insert_text((56, cursor.y), "EXPERIENCE", fontsize=9.5, color=WHITE, fontname=SANS_BOLD)
    cursor.y += 20
    for title, context, bullets in candidate.experience:
        cursor.write(title, size=9.5, font=SANS_BOLD, gap_after=1)
        cursor.write(context, size=8.5, color=GREY, gap_after=3)
        for bullet in bullets:
            cursor.write(f"›  {bullet}", size=9, gap_after=2)
        cursor.y += 4
    block = pymupdf.Rect(40, cursor.y - 12, PAGE.width - 40, cursor.y + 6)
    page.draw_rect(block, color=None, fill=candidate.accent)
    page.insert_text(
        (56, cursor.y), "SKILLS & EDUCATION", fontsize=9.5, color=WHITE, fontname=SANS_BOLD
    )
    cursor.y += 20
    for skill in candidate.skills:
        cursor.write(f"›  {skill}", size=9, gap_after=2)
    for line in candidate.education:
        cursor.write(line, size=9, gap_after=2)


def europass(page: pymupdf.Page, candidate: Candidate) -> None:
    """Boxed, form-like, the shape of a public-sector template."""
    page.draw_rect(pymupdf.Rect(45, 45, PAGE.width - 45, 100), color=candidate.accent, width=1.1)
    page.insert_text((58, 68), candidate.name, fontsize=14, fontname=SANS_BOLD)
    page.insert_text((58, 86), f"{candidate.headline}  |  {candidate.location}", fontsize=9)

    cursor = _Cursor(page, 58, PAGE.width - 58, 124)
    for label, lines in (
        ("PERSONAL STATEMENT", (candidate.summary,)),
        ("WORK EXPERIENCE", ()),
    ):
        page.draw_rect(
            pymupdf.Rect(45, cursor.y - 11, PAGE.width - 45, cursor.y + 4),
            color=None,
            fill=(0.90, 0.93, 0.98),
        )
        page.insert_text(
            (58, cursor.y), label, fontsize=9, color=candidate.accent, fontname=SANS_BOLD
        )
        cursor.y += 18
        for line in lines:
            cursor.write(line, size=9, gap_after=6)
    for title, context, bullets in candidate.experience:
        cursor.write(title, size=9, font=SANS_BOLD, gap_after=1)
        cursor.write(context, size=8.5, color=GREY, gap_after=3)
        for bullet in bullets:
            cursor.write(f"-  {bullet}", size=9, gap_after=2)
        cursor.y += 4
    for label, lines in (
        ("EDUCATION AND TRAINING", candidate.education),
        ("DIGITAL SKILLS", candidate.skills),
    ):
        page.draw_rect(
            pymupdf.Rect(45, cursor.y - 11, PAGE.width - 45, cursor.y + 4),
            color=None,
            fill=(0.90, 0.93, 0.98),
        )
        page.insert_text(
            (58, cursor.y), label, fontsize=9, color=candidate.accent, fontname=SANS_BOLD
        )
        cursor.y += 18
        for line in lines:
            cursor.write(f"-  {line}", size=9, gap_after=2)


def timeline(page: pymupdf.Page, candidate: Candidate) -> None:
    """A vertical rail with dots, content offset to the right of it."""
    page.insert_text((60, 66), candidate.name, fontsize=16, fontname=SANS_BOLD)
    page.insert_text(
        (60, 84), f"{candidate.headline} · {candidate.location}", fontsize=9, color=GREY
    )
    page.draw_line(
        pymupdf.Point(72, 108),
        pymupdf.Point(72, PAGE.height - 70),
        color=candidate.accent,
        width=1.4,
    )

    cursor = _Cursor(page, 92, PAGE.width - 55, 118)
    cursor.write(candidate.summary, size=9.5, gap_after=12)
    for title, context, bullets in candidate.experience:
        page.draw_circle(pymupdf.Point(72, cursor.y - 3), 3.6, color=None, fill=candidate.accent)
        cursor.write(title, size=9.5, font=SANS_BOLD, gap_after=1)
        cursor.write(context, size=8.5, color=GREY, gap_after=3)
        for bullet in bullets:
            cursor.write(f"•  {bullet}", size=9, gap_after=2)
        cursor.y += 6
    page.draw_circle(pymupdf.Point(72, cursor.y - 3), 3.6, color=None, fill=candidate.accent)
    cursor.write("EDUCATION", size=10, color=candidate.accent, font=SANS_BOLD, gap_after=4)
    for line in candidate.education:
        cursor.write(line, size=9, gap_after=2)
    cursor.y += 4
    _skills(cursor, candidate, BLACK, candidate.accent)


def ats_plain(page: pymupdf.Page, candidate: Candidate) -> None:
    """No colour, no rules, no columns. What an ATS export looks like."""
    cursor = _Cursor(page, 60, PAGE.width - 60, 70)
    cursor.write(candidate.name.upper(), size=11, font=SANS_BOLD, gap_after=2)
    cursor.write(candidate.headline, size=9.5, gap_after=1)
    cursor.write(candidate.location, size=9.5, gap_after=10)
    cursor.write("SUMMARY", size=9.5, font=SANS_BOLD, gap_after=3)
    cursor.write(candidate.summary, size=9.5, gap_after=10)
    _body(cursor, candidate, BLACK)
    cursor.y += 6
    cursor.write("SKILLS", size=9.5, font=SANS_BOLD, gap_after=3)
    for skill in candidate.skills:
        cursor.write(skill, size=9.5, gap_after=2)


def dark_sidebar(page: pymupdf.Page, candidate: Candidate) -> None:
    """Dark rail with light text. Exercises per-span background detection (plan §6)."""
    page.draw_rect(pymupdf.Rect(0, 0, PAGE.width, PAGE.height), color=None, fill=(0.97, 0.97, 0.97))
    rail = pymupdf.Rect(PAGE.width - 200, 0, PAGE.width, PAGE.height)
    page.draw_rect(rail, color=None, fill=candidate.accent)

    left = _Cursor(page, 50, PAGE.width - 225, 76)
    left.write(candidate.name, size=17, font=SANS_BOLD, gap_after=3)
    left.write(candidate.headline, size=10, color=GREY, gap_after=1)
    left.write(candidate.location, size=9, color=GREY, gap_after=14)
    left.write(candidate.summary, size=9.5, gap_after=12)
    _body(left, candidate, candidate.accent)

    right = _Cursor(page, PAGE.width - 182, PAGE.width - 26, 80)
    _skills(right, candidate, WHITE, WHITE)


RENDERERS = {
    "harvard": harvard,
    "canva_sidebar": canva_sidebar,
    "modern_header": modern_header,
    "minimalist": minimalist,
    "academic_dense": academic_dense,
    "creative_blocks": creative_blocks,
    "europass": europass,
    "timeline": timeline,
    "ats_plain": ats_plain,
    "dark_sidebar": dark_sidebar,
}


def render(candidate: Candidate) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=PAGE.width, height=PAGE.height)
    RENDERERS[candidate.layout](page, candidate)

    if candidate.hidden_payload:
        # White on white, low in the page: the classic attack (plan §6, layer 1).
        page.insert_text((60, PAGE.height - 90), candidate.hidden_payload, fontsize=9, color=WHITE)

    data: bytes = document.tobytes()
    document.close()
    return data
