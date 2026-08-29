"""Assemble, submit and collect Batch API jobs.

Four things differ from the synchronous path and each one is a way to get this
wrong: no `text_format`, a raw strict schema instead, a file-upload call
sequence, and results that come back in arbitrary order.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any, Literal

from app.ai.batch_schema import text_format
from app.ai.client import MODEL_ID, get_client
from app.ai.evaluator import MAX_OUTPUT_TOKENS, REASONING_EFFORT, EvaluationRequest, build_input
from app.ai.schema import EvaluationOutput

BATCH_ENDPOINT: Literal["/v1/responses"] = "/v1/responses"
# The only value the API accepts; it is not configurable.
COMPLETION_WINDOW: Literal["24h"] = "24h"


@dataclass(frozen=True)
class BatchItem:
    """One résumé to evaluate. `custom_id` is how the result finds its way home."""

    custom_id: str
    request: EvaluationRequest


@dataclass(frozen=True)
class BatchResult:
    custom_id: str
    output: EvaluationOutput | None
    error: str | None
    input_tokens: int = 0
    output_tokens: int = 0


def build_body(request: EvaluationRequest) -> dict[str, Any]:
    return {
        "model": MODEL_ID,
        "input": build_input(request),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning": {"effort": REASONING_EFFORT},
        "store": False,
        "text": text_format(),
    }


def build_jsonl(items: list[BatchItem]) -> bytes:
    lines = [
        json.dumps(
            {
                "custom_id": item.custom_id,
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": build_body(item.request),
            },
            ensure_ascii=False,
        )
        for item in items
    ]
    return ("\n".join(lines)).encode("utf-8")


def estimate_input_tokens(items: list[BatchItem]) -> int:
    """Rough token count for the enqueued-token limit, from characters.

    Deliberately crude and deliberately an overestimate: the splitter only needs
    to know whether a send is plausibly too big, and guessing low is the failure
    that gets the whole batch rejected.
    """
    characters = sum(
        len(message["content"]) for item in items for message in build_input(item.request)
    )
    return characters // 3


def submit(items: list[BatchItem]) -> str:
    """Upload the requests and start a batch. Returns the batch id."""
    client = get_client()
    uploaded = client.files.create(file=io.BytesIO(build_jsonl(items)), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=BATCH_ENDPOINT,
        completion_window=COMPLETION_WINDOW,
    )
    return batch.id


def status(batch_id: str) -> str:
    return str(get_client().batches.retrieve(batch_id).status)


def collect(batch_id: str) -> list[BatchResult]:
    """Read a finished batch.

    Results arrive in arbitrary order, so every one carries its `custom_id` and
    callers must key by it. A row that failed is returned as a result with an
    error rather than dropped: a candidate whose evaluation failed still needs
    to appear in the panel with the reason.

    **Two files, not one.** The API writes successful rows to `output_file_id`
    and failed or expired ones to `error_file_id`. Reading only the first loses
    every failure, and the caller then reports the useless "missing from batch
    output" instead of what actually went wrong.
    """
    client = get_client()
    batch = client.batches.retrieve(batch_id)

    results: list[BatchResult] = []
    for file_id in (batch.output_file_id, batch.error_file_id):
        if not file_id:
            continue
        for line in client.files.content(file_id).text.splitlines():
            if not line.strip():
                continue
            results.append(_parse_row(json.loads(line)))
    return results


def _parse_row(row: dict[str, Any]) -> BatchResult:
    custom_id = str(row.get("custom_id", ""))
    response = row.get("response") or {}
    if row.get("error") or response.get("status_code") != 200:
        detail = row.get("error") or response.get("body")
        return BatchResult(custom_id=custom_id, output=None, error=str(detail)[:500])

    body = response.get("body") or {}
    usage = body.get("usage") or {}
    try:
        text = _first_output_text(body)
        parsed = EvaluationOutput.model_validate_json(text)
    except Exception as exc:  # noqa: BLE001 - a malformed row must not kill the batch
        return BatchResult(custom_id=custom_id, output=None, error=f"unparseable: {exc}"[:500])

    return BatchResult(
        custom_id=custom_id,
        output=parsed,
        error=None,
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )


def _first_output_text(body: dict[str, Any]) -> str:
    for item in body.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                return str(content["text"])
    raise ValueError("no output_text in response")
