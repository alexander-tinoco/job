"""Render the golden-set résumés to PDF and run them through the real pipeline.

    .venv/bin/python scripts/build_golden_set.py

Writes PDFs to tests/golden/pdfs/ and prints what extraction recovered from each
layout. No model is called here.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest.pipeline import extract  # noqa: E402
from tests.golden.candidates import CANDIDATES, INJECTION_PAYLOAD  # noqa: E402
from tests.golden.layouts import render  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "golden" / "pdfs"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # An eleventh file: the mid-ranked candidate with a payload hidden in white
    # on white, to exercise the whole chain rather than the rules alone.
    injected = replace(CANDIDATES[3], key="ibarra_injected", hidden_payload=INJECTION_PAYLOAD)

    print(f"{'candidate':18} {'layout':16} {'chars':>6} {'hidden':>7} {'patterns':>9}  verdict")
    print("-" * 78)
    for candidate in (*CANDIDATES, injected):
        path = OUT / f"{candidate.key}.pdf"
        path.write_bytes(render(candidate))
        result = extract(path)
        flag = "OCR" if result.used_ocr else ""
        print(
            f"{candidate.key:18} {candidate.layout:16} "
            f"{len(result.visible_text):6} {result.hidden_char_count:7} "
            f"{len(result.matched_patterns):9}  {flag}"
        )
    print(f"\nwrote {len(CANDIDATES) + 1} PDFs to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
