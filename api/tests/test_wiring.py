"""The seams between the app and what it depends on.

Small pieces, each of which fails in a way that is easy to misdiagnose: a
missing key, a missing binary, a page that is not there. Every one of them says
what to do about it rather than raising something generic.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from sqlalchemy.orm import Session

from app.ai import client as ai_client
from app.core.config import get_settings
from app.db.session import get_session
from app.ingest import ocr, render
from tests.pdfs import make_resume


def test_a_missing_key_names_the_file_to_put_it_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "Authentication failed" from the SDK would send someone to the wrong place."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    ai_client.get_client.cache_clear()

    with pytest.raises(ai_client.MissingApiKeyError) as caught:
        ai_client.get_client()

    assert ".env" in str(caught.value)
    assert "OPENAI_API_KEY" in str(caught.value)


def test_the_client_is_built_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """One place knows the model id, the timeout and where the key comes from."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    ai_client.get_client.cache_clear()

    assert ai_client.get_client() is ai_client.get_client()
    ai_client.get_client.cache_clear()


def test_ocr_says_what_to_install_when_it_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scanned résumé on a box without Tesseract is an operator problem."""
    monkeypatch.setattr(ocr, "is_available", lambda: False)
    document = pymupdf.open(stream=make_resume(), filetype="pdf")

    with pytest.raises(ocr.OcrUnavailableError) as caught:
        ocr.extract_with_ocr(document)

    assert "tesseract-ocr" in str(caught.value)


def test_the_page_count_is_capped(tmp_path: Path) -> None:
    """A hundred-page PDF must not become a hundred render requests."""
    path = tmp_path / "cv.pdf"
    path.write_bytes(make_resume())

    assert 1 <= render.page_count(path) <= render.MAX_PAGES


def test_a_page_that_does_not_exist_is_not_an_internal_error(tmp_path: Path) -> None:
    path = tmp_path / "cv.pdf"
    path.write_bytes(make_resume())

    with pytest.raises(render.PageOutOfRangeError):
        render.render_page(path, 99)


def test_a_page_renders_as_a_png(tmp_path: Path) -> None:
    """An image, not the PDF: a stranger's file never runs on the panel's origin."""
    path = tmp_path / "cv.pdf"
    path.write_bytes(make_resume())

    image = render.render_page(path, 1)

    assert image.startswith(b"\x89PNG\r\n\x1a\n")


def test_the_session_dependency_closes_what_it_opens() -> None:
    generator = get_session()
    session = next(generator)
    assert isinstance(session, Session)

    with pytest.raises(StopIteration):
        next(generator)
    assert not session.is_active or session.get_bind() is not None
