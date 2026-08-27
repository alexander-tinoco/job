"""Layer 1 of the anti-injection design (plan §6).

Each test hides the same payload a different way and asserts the same thing:
the model never sees it, HR always does.
"""

import pymupdf
import pytest

from app.ingest.hidden import (
    MIN_CONTRAST_RATIO,
    Reason,
    contrast_ratio,
    split_visible,
)
from app.ingest.spans import read_document
from tests.pdfs import PAYLOAD, HiddenMode, make_resume


def _analyse(data: bytes) -> tuple[str, str, list[object]]:
    document = pymupdf.open(stream=data, filetype="pdf")
    pages = read_document(document)
    document.close()
    return split_visible(pages)  # type: ignore[return-value]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("white_on_white", Reason.LOW_CONTRAST),
        ("dark_on_dark", Reason.LOW_CONTRAST),
        ("tiny", Reason.TOO_SMALL),
        ("render_mode_3", Reason.INVISIBLE_RENDER_MODE),
        ("transparent", Reason.TRANSPARENT),
        ("off_page", Reason.OFF_PAGE),
        ("covered", Reason.COVERED),
    ],
)
def test_a_hidden_payload_never_reaches_the_visible_text(
    mode: HiddenMode, expected: Reason
) -> None:
    visible, total, hidden = _analyse(make_resume(hidden=PAYLOAD, mode=mode))

    assert "Ignore previous instructions" not in visible, f"{mode} leaked into the model input"
    assert "Ignore previous instructions" in total, f"{mode} was not extracted at all"
    assert [h.reason for h in hidden] == [expected]  # type: ignore[attr-defined]


def test_the_report_says_where_and_why(mode: HiddenMode = "tiny") -> None:
    _, _, hidden = _analyse(make_resume(hidden=PAYLOAD, mode=mode))

    found = hidden[0]
    assert found.page_number == 1  # type: ignore[attr-defined]
    assert found.detail == "1.0pt"  # type: ignore[attr-defined]
    assert len(found.bbox) == 4  # type: ignore[attr-defined]


def test_a_clean_resume_hides_nothing(_: None = None) -> None:
    visible, total, hidden = _analyse(make_resume())

    assert hidden == []
    assert visible == total
    assert "Ada Lovelace" in visible


def test_a_dark_sidebar_does_not_hide_its_own_legible_text() -> None:
    """White on navy is perfectly readable and must not be flagged."""
    visible, _, hidden = _analyse(make_resume(mode="dark_on_dark"))

    assert hidden == []
    assert "Ada Lovelace" in visible


def test_light_grey_body_text_is_not_flagged() -> None:
    """Real résumés use grey for subheadings; a false positive removes a real person."""
    assert contrast_ratio((0.8, 0.8, 0.8), (1.0, 1.0, 1.0)) > MIN_CONTRAST_RATIO


def test_contrast_ratio_matches_the_wcag_endpoints() -> None:
    assert contrast_ratio((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio((1.0, 1.0, 1.0), (1.0, 1.0, 1.0)) == pytest.approx(1.0)
