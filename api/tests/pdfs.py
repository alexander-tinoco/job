"""PDF builders for tests.

Generated rather than committed as binaries: Phase 4 needs résumés with text
hidden at a specific colour and font size, and only generation lets a test state
exactly what it is hiding.
"""

import pymupdf


def make_resume(
    visible: str = "Ada Lovelace\nSix years of Python and Postgres.",
    hidden: str | None = None,
    hidden_mode: str = "white",
) -> bytes:
    """Build a one-page PDF.

    `hidden` is drawn invisibly to a human: white on white, or at 1pt.
    """
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), visible, fontsize=11, color=(0, 0, 0))

    if hidden is not None:
        if hidden_mode == "white":
            page.insert_text((72, 300), hidden, fontsize=11, color=(1, 1, 1))
        elif hidden_mode == "tiny":
            page.insert_text((72, 300), hidden, fontsize=1, color=(0, 0, 0))
        else:  # pragma: no cover - guards against a typo in a test
            raise ValueError(f"Unknown hidden_mode: {hidden_mode}")

    data: bytes = document.tobytes()
    document.close()
    return data


def not_a_pdf() -> bytes:
    """An executable renamed to .pdf: passes a Content-Type check, fails the magic number."""
    return b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 512


def oversized_pdf(size_bytes: int) -> bytes:
    """A real PDF header followed by padding, to exercise the size limit."""
    base = make_resume()
    padding = b"\n%" + b"x" * max(0, size_bytes - len(base) - 2)
    return base + padding
