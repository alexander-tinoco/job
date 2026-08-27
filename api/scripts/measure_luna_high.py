"""Does more reasoning buy stability? Measure luna at high and xhigh, repeated.

Accuracy cannot be judged without a human ranking (Phase 6), but **variance
can**: the same request run three times should give the same scores. At medium,
luna scored the same clean résumé Postgres 3, 3 and 2. If higher effort removes
that swing, it buys something measurable today.

    .venv/bin/python scripts/measure_luna_high.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.measure_effort import call  # noqa: E402
from scripts.record_fixtures import INJECTED, STRONG  # noqa: E402

MODEL = "gpt-5.6-luna"
EFFORTS = ["high", "xhigh"]
REPEATS = 3
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "luna_high.json"


def main() -> int:
    results: dict[str, list[dict[str, object]]] = {}
    for effort in EFFORTS:
        for case, resume in {"strong": STRONG, "injected": INJECTED}.items():
            key = f"{effort}/{case}"
            results[key] = []
            for run in range(REPEATS):
                print(f"{key} run {run + 1}/{REPEATS}...", flush=True)
                try:
                    results[key].append(call(resume, effort, MODEL))
                except Exception as exc:  # noqa: BLE001 - report and continue
                    print(f"  FAILED: {type(exc).__name__}: {str(exc)[:120]}")
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    total = 0.0
    for key, runs in results.items():
        if not runs:
            print(f"{key:18} (no successful runs)")
            continue
        scores = [
            tuple(c["score"] for c in r["output"]["criteria"])  # type: ignore[index]
            for r in runs
        ]
        costs = [float(r["cost_usd"]) for r in runs]  # type: ignore[arg-type]
        reasoning = [r["reasoning_tokens"] for r in runs]
        total += sum(costs)
        stable = "STABLE" if len(set(scores)) == 1 else "varies"
        print(
            f"{key:18} scores={scores}  {stable:6} "
            f"reasoning={reasoning}  ${sum(costs) / len(costs):.5f}/CV"
        )
    print(f"\ntotal spent: ${total:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
