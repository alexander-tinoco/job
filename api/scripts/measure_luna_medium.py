"""Measure gpt-5.6-luna at medium effort, repeated, to see variance not a sample.

The earlier single-sample runs disagreed with each other, so every cell here is
run three times. Run manually:

    .venv/bin/python scripts/measure_luna_medium.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.measure_effort import PRICES, call  # noqa: E402
from scripts.record_fixtures import INJECTED, STRONG  # noqa: E402

REPEATS = 3
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "luna_medium.json"


def main() -> int:
    results: dict[str, list[dict[str, object]]] = {}
    for case, resume in {"strong": STRONG, "injected": INJECTED}.items():
        results[case] = []
        for run in range(REPEATS):
            print(f"luna/medium {case} run {run + 1}/{REPEATS}...", flush=True)
            try:
                results[case].append(call(resume, "medium", "gpt-5.6-luna"))
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"  FAILED: {type(exc).__name__}: {str(exc)[:120]}")
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    total = 0.0
    for case, runs in results.items():
        for index, r in enumerate(runs, start=1):
            total += float(r["cost_usd"])  # type: ignore[arg-type]
            scores = {c["criterion_name"]: c["score"] for c in r["output"]["criteria"]}  # type: ignore[index]
            print(
                f"{case:9} run{index}  out={r['output_tokens']:6} "
                f"reasoning={r['reasoning_tokens']:6} ${r['cost_usd']:.5f}  {scores}"
            )
    print(f"\ntotal: ${total:.5f}  (prices used: {PRICES['gpt-5.6-luna']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
