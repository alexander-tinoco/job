"""Measure what reasoning effort actually costs and whether it degrades quality.

Run manually, never from a test or from CI:

    .venv/bin/python scripts/measure_effort.py

The API key is read from .env by the settings object and is never printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.client import get_client  # noqa: E402
from app.ai.evaluator import MAX_OUTPUT_TOKENS, build_input  # noqa: E402
from app.ai.schema import EvaluationOutput  # noqa: E402
from scripts.record_fixtures import CRITERIA, INJECTED, STRONG  # noqa: E402

# USD per 1M tokens, standard tier.
PRICES = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.6-luna": (0.20, 1.20),
}

# (model, effort) combinations to measure.
MATRIX = [
    ("gpt-5.4-mini", "none"),
    ("gpt-5.4-mini", "low"),
    ("gpt-5.6-luna", "none"),
    ("gpt-5.6-luna", "low"),
]
CASES = {"strong": STRONG, "injected": INJECTED}
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "effort_measurements.json"


def call(resume: str, effort: str, model: str) -> dict[str, object]:
    from app.ai.evaluator import EvaluationRequest, RubricCriterion  # noqa: F401

    request = EvaluationRequest(
        job_title="Backend Engineer",
        company_context="Small team, Python shop, ships weekly.",
        criteria=CRITERIA,
        resume_text=resume,
    )
    response = get_client().responses.parse(
        model=model,
        input=build_input(request),  # type: ignore[arg-type]
        text_format=EvaluationOutput,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        reasoning={"effort": effort},  # type: ignore[arg-type]
        store=False,
    )
    usage = response.usage
    assert usage is not None
    reasoning = getattr(usage.output_tokens_details, "reasoning_tokens", 0) or 0
    price_in, price_out = PRICES[model]
    cost = (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
    parsed = response.output_parsed
    return {
        "model": model,
        "effort": effort,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": reasoning,
        "cost_usd": round(cost, 6),
        "output": parsed.model_dump() if parsed is not None else None,
    }


def main() -> int:
    results: dict[str, list[dict[str, object]]] = {}
    for case, resume in CASES.items():
        results[case] = []
        for model, effort in MATRIX:
            print(f"calling {case} on {model} at effort={effort}...", flush=True)
            try:
                results[case].append(call(resume, effort, model))
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"  FAILED: {type(exc).__name__}: {str(exc)[:120]}")
                results[case].append(
                    {"model": model, "effort": effort, "error": f"{type(exc).__name__}"}
                )
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
