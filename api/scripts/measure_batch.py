"""Measure the Batch API: real discount, turnaround, and this account's limits.

Throwaway measurement, not the Phase 7 implementation. Run manually:

    .venv/bin/python scripts/measure_batch.py          # submit
    .venv/bin/python scripts/measure_batch.py --check  # poll and report

The API key is read from .env by the settings object and is never printed.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.client import MODEL_ID, get_client  # noqa: E402
from app.ai.evaluator import MAX_OUTPUT_TOKENS, REASONING_EFFORT, build_input  # noqa: E402
from app.ai.schema import EvaluationOutput  # noqa: E402
from scripts.record_fixtures import CRITERIA, INJECTED, STRONG, WEAK  # noqa: E402

STATE = Path(__file__).resolve().parent / ".batch_id"
# Batch is 50% off the synchronous rates in plan §3.
BATCH_INPUT_PER_M = 0.375
BATCH_OUTPUT_PER_M = 2.25


def _body(resume: str) -> dict[str, object]:
    from app.ai.evaluator import EvaluationRequest

    request = EvaluationRequest(
        job_title="Backend Engineer",
        company_context="Small team, Python shop, ships weekly.",
        criteria=CRITERIA,
        resume_text=resume,
    )
    schema = EvaluationOutput.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "model": MODEL_ID,
        "input": build_input(request),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning": {"effort": REASONING_EFFORT},
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "evaluation",
                "strict": False,
                "schema": schema,
            }
        },
    }


def submit() -> None:
    client = get_client()
    lines = [
        json.dumps({"custom_id": name, "method": "POST", "url": "/v1/responses", "body": _body(cv)})
        for name, cv in {"strong": STRONG, "weak": WEAK, "injected": INJECTED}.items()
    ]
    payload = ("\n".join(lines)).encode("utf-8")
    print(f"submitting {len(lines)} requests, {len(payload)} bytes")

    uploaded = client.files.create(file=io.BytesIO(payload), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id, endpoint="/v1/responses", completion_window="24h"
    )
    STATE.write_text(batch.id)
    print(f"batch {batch.id} status={batch.status}")


def check() -> None:
    client = get_client()
    batch = client.batches.retrieve(STATE.read_text().strip())
    print(f"status={batch.status} counts={batch.request_counts}")
    if batch.status != "completed":
        if batch.errors:
            print("errors:", batch.errors)
        return

    created, completed = batch.created_at, batch.completed_at or 0
    print(f"turnaround: {completed - created}s")

    assert batch.output_file_id
    content = client.files.content(batch.output_file_id).text
    total_in = total_out = total_reasoning = 0
    for line in content.splitlines():
        row = json.loads(line)
        usage = row["response"]["body"]["usage"]
        total_in += usage["input_tokens"]
        total_out += usage["output_tokens"]
        total_reasoning += usage.get("output_tokens_details", {}).get("reasoning_tokens", 0)
        print(f"  {row['custom_id']}: in={usage['input_tokens']} out={usage['output_tokens']}")

    n = len(content.splitlines())
    cost = (total_in * BATCH_INPUT_PER_M + total_out * BATCH_OUTPUT_PER_M) / 1_000_000
    print(f"\ntotals: in={total_in} out={total_out} reasoning={total_reasoning}")
    print(f"batch cost: ${cost:.6f} for {n} résumés  =>  ${cost / n:.6f}/résumé")
    print(f"projected 500 résumés: ${cost / n * 500:.2f}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        submit()
        time.sleep(20)
        check()
