"""Run the golden set through both models and score them against the answer key.

    .venv/bin/python scripts/compare_models.py

Each candidate is evaluated REPEATS times per model, because a single run of a
stochastic model has already produced contradictory conclusions twice in this
project. Reports rank agreement, variance, review flags and cost.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai.types.shared_params import Reasoning  # noqa: E402

from app.ai.evaluator import (  # noqa: E402
    MAX_OUTPUT_TOKENS,
    REASONING_EFFORT,
    EvaluationRequest,
    RubricCriterion,
    build_input,
)
from app.ai.schema import EvaluationOutput  # noqa: E402
from app.ai.verify import verify  # noqa: E402
from app.ingest.pipeline import extract  # noqa: E402

from app.ai.client import get_client  # noqa: E402  isort:skip
from tests.golden.candidates import CANDIDATES, INTENDED_ORDER  # noqa: E402  isort:skip

PDFS = Path(__file__).resolve().parent.parent / "tests" / "golden" / "pdfs"
OUT = Path(__file__).resolve().parent.parent / "tests" / "golden" / "comparison.json"

MODELS = {"gpt-5.6-luna": (0.20, 1.20), "gpt-5.4-mini": (0.75, 4.50)}
REPEATS = 3

JOB_TITLE = "Data Analyst"
COMPANY_CONTEXT = (
    "Mid-size marketplace, 60 people. The analytics team is three people and sits with "
    "product. Warehouse is Snowflake with dbt; BI is Looker. We ship experiments weekly "
    "and expect analysts to design them, not just read the results."
)
CRITERIA = (
    RubricCriterion(
        name="SQL and data modelling",
        description=(
            "Depth in SQL and warehouse modelling, judged on ownership and results rather "
            "than a list of keywords."
        ),
        mandatory=True,
    ),
    RubricCriterion(
        name="Statistics and experimentation",
        description="Designing and analysing experiments; causal reasoning beyond averages.",
        mandatory=False,
    ),
    RubricCriterion(
        name="BI and visualisation",
        description="Building reporting other people rely on: Looker, Tableau, Power BI.",
        mandatory=False,
    ),
    RubricCriterion(
        name="Business impact",
        description="Evidence that the analysis changed a decision, ideally with a number.",
        mandatory=False,
    ),
)
WEIGHTS = {
    "SQL and data modelling": 30,
    "Statistics and experimentation": 25,
    "BI and visualisation": 25,
    "Business impact": 20,
}


def evaluate_with(
    model: str, request: EvaluationRequest
) -> tuple[EvaluationOutput, dict[str, int]]:
    response = get_client().responses.parse(
        model=model,
        input=build_input(request),  # type: ignore[arg-type]
        text_format=EvaluationOutput,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        reasoning=Reasoning(effort=REASONING_EFFORT),
        store=False,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError(f"no parseable output ({response.status})")
    usage = response.usage
    assert usage is not None
    return parsed, {"input": usage.input_tokens, "output": usage.output_tokens}


def spearman(actual: list[str], expected: list[str]) -> float:
    """Rank correlation. 1.0 is perfect agreement, 0 is none, -1.0 is reversed."""
    position = {key: index for index, key in enumerate(actual)}
    n = len(expected)
    d_squared = sum((position[key] - index) ** 2 for index, key in enumerate(expected))
    return 1 - (6 * d_squared) / (n * (n**2 - 1))


def main() -> int:
    texts = {c.key: extract(PDFS / f"{c.key}.pdf").visible_text for c in CANDIDATES}
    texts["ibarra_injected"] = extract(PDFS / "ibarra_injected.pdf").visible_text

    results: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    for model, (price_in, price_out) in MODELS.items():
        for key, text in texts.items():
            request = EvaluationRequest(
                job_title=JOB_TITLE,
                company_context=COMPANY_CONTEXT,
                criteria=CRITERIA,
                resume_text=text,
            )
            for run in range(REPEATS):
                print(f"{model} · {key} · run {run + 1}/{REPEATS}", flush=True)
                try:
                    output, usage = evaluate_with(model, request)
                except Exception as exc:  # noqa: BLE001 - record and continue
                    print(f"   FAILED: {type(exc).__name__}: {str(exc)[:100]}")
                    continue
                checked = verify(output, text, WEIGHTS)
                cost = (usage["input"] * price_in + usage["output"] * price_out) / 1_000_000
                results[model][key].append(
                    {
                        "score": float(checked.overall_score),
                        "criteria": {c.criterion_name: c.score for c in checked.criteria},
                        "needs_review": checked.needs_human_review,
                        "review_reasons": list(checked.review_reasons),
                        "risks": list(output.risks),
                        "unverified_quotes": [
                            q.quote for c in checked.criteria for q in c.quotes if not q.found
                        ],
                        "cost_usd": round(cost, 6),
                        "tokens": usage,
                    }
                )

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    report(results)
    return 0


def report(results: dict[str, dict[str, list[dict[str, object]]]]) -> None:
    for model, per_candidate in results.items():
        print(f"\n{'=' * 82}\n{model}\n{'=' * 82}")
        means: dict[str, float] = {}
        print(f"{'candidate':18} {'intended':>8} {'scores':28} {'mean':>7} {'sd':>6} {'review':>7}")
        for candidate in sorted(CANDIDATES, key=lambda c: c.intended_rank):
            runs = per_candidate.get(candidate.key, [])
            if not runs:
                continue
            scores = [float(r["score"]) for r in runs]  # type: ignore[arg-type]
            means[candidate.key] = statistics.fmean(scores)
            sd = statistics.pstdev(scores) if len(scores) > 1 else 0.0
            flagged = sum(1 for r in runs if r["needs_review"])
            print(
                f"{candidate.key:18} {candidate.intended_rank:8} "
                f"{str([round(s, 1) for s in scores]):28} "
                f"{means[candidate.key]:7.1f} {sd:6.1f} {flagged:5}/{len(runs)}"
            )
        ranked = [k for k, _ in sorted(means.items(), key=lambda kv: -kv[1])]
        intended = [k for k in INTENDED_ORDER if k in means]
        rho = spearman(ranked, intended)
        top3 = len(set(ranked[:3]) & set(intended[:3]))
        top5 = len(set(ranked[:5]) & set(intended[:5]))
        costs: list[float] = [
            float(str(r["cost_usd"])) for runs in per_candidate.values() for r in runs
        ]
        total_cost = sum(costs)
        n_runs = sum(len(runs) for runs in per_candidate.values())
        print(f"\n  model order : {' > '.join(ranked)}")
        print(f"  intended    : {' > '.join(intended)}")
        print(f"  spearman rho: {rho:+.3f}   top-3 overlap: {top3}/3   top-5 overlap: {top5}/5")
        print(
            f"  cost        : ${total_cost / n_runs:.5f}/résumé over {n_runs} calls "
            f"(${total_cost:.4f} total)"
        )

        clean = per_candidate.get("ibarra", [])
        injected = per_candidate.get("ibarra_injected", [])
        if clean and injected:
            c = statistics.fmean(float(r["score"]) for r in clean)  # type: ignore[arg-type]
            i = statistics.fmean(float(r["score"]) for r in injected)  # type: ignore[arg-type]
            caught = sum(1 for r in injected if r["risks"])
            print(
                f"  injection   : clean {c:.1f} -> injected {i:.1f} "
                f"({i - c:+.1f}), reported as a risk in {caught}/{len(injected)} runs"
            )


if __name__ == "__main__":
    raise SystemExit(main())
