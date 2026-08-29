"""The Batch API round trip.

Every candidate is evaluated through this path, and until now it was the least
covered code in the project: `test_batch_schema.py` checks the schema hardening
and `test_scheduler.py` mocks this module away entirely, so the seam between
them — interpreting what the API actually returns — was tested from neither
side.

No test here calls OpenAI (AI rule 12). The two `.jsonl` fixtures carry the
recorded shapes; `tests/fixtures/README.md` records where each came from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.ai import batch
from app.ai.client import MODEL_ID
from app.ai.evaluator import EvaluationRequest, RubricCriterion

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUT_FILE = (FIXTURES / "batch_output.jsonl").read_text(encoding="utf-8")
ERROR_FILE = (FIXTURES / "batch_error.jsonl").read_text(encoding="utf-8")

ROW_A = "01a04b28-a41c-7567-86c5-ff7982b43b64"  # strong, parses
ROW_B = "01a04b28-a41c-7567-86c5-ff7982b43b65"  # weak, parses
ROW_C = "01a04b28-a41c-7567-86c5-ff7982b43b66"  # text is not valid JSON
ROW_D = "01a04b28-a41c-7567-86c5-ff7982b43b67"  # reasoning only, no message
ROW_EXPIRED = "01a04b28-a41c-7567-86c5-ff7982b43b68"
ROW_REJECTED = "01a04b28-a41c-7567-86c5-ff7982b43b69"


# --- A stand-in for the OpenAI client -------------------------------------
#
# Shaped after the real object rather than mocked loosely: a fake that accepts
# anything would let the code drift away from the API without a test noticing.


@dataclass
class _Uploaded:
    id: str


@dataclass
class _Content:
    text: str


class _Batch:
    def __init__(self, status: str, output_file_id: str | None, error_file_id: str | None):
        self.id = "batch_test"
        self.status = status
        self.output_file_id = output_file_id
        self.error_file_id = error_file_id


class FakeClient:
    def __init__(
        self,
        *,
        status: str = "completed",
        output_file_id: str | None = "file_out",
        error_file_id: str | None = None,
        files: dict[str, str] | None = None,
    ) -> None:
        self._batch = _Batch(status, output_file_id, error_file_id)
        self._files = files or {}
        self.uploaded: bytes | None = None
        self.upload_purpose: str | None = None
        self.created_with: dict[str, Any] | None = None
        self.fetched: list[str] = []

        client = self

        class _Files:
            def create(self, *, file: Any, purpose: str) -> _Uploaded:
                client.uploaded = file.read()
                client.upload_purpose = purpose
                return _Uploaded(id="file_in")

            def content(self, file_id: str) -> _Content:
                client.fetched.append(file_id)
                return _Content(text=client._files[file_id])

        class _Batches:
            def create(self, **kwargs: Any) -> _Batch:
                client.created_with = kwargs
                return client._batch

            def retrieve(self, batch_id: str) -> _Batch:
                return client._batch

        self.files = _Files()
        self.batches = _Batches()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch):
    def install(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        monkeypatch.setattr("app.ai.batch.get_client", lambda: client)
        return client

    return install


RESUME_TEXT: str = json.loads((FIXTURES / "strong_candidate.json").read_text(encoding="utf-8"))[
    "resume_text"
]


def _request() -> EvaluationRequest:
    return EvaluationRequest(
        job_title="Backend Engineer",
        company_context="Small team, Python shop.",
        criteria=(
            RubricCriterion(name="Python", description="Depth in Python.", mandatory=True),
            RubricCriterion(name="Postgres", description="Relational modelling.", mandatory=False),
        ),
        resume_text=RESUME_TEXT,
    )


# --- Building the request -------------------------------------------------


def test_every_line_is_a_self_contained_request() -> None:
    items = [batch.BatchItem(custom_id=ROW_A, request=_request())]
    lines = batch.build_jsonl(items).decode("utf-8").splitlines()

    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["custom_id"] == ROW_A
    assert row["method"] == "POST"
    assert row["url"] == "/v1/responses"
    assert row["body"]["model"] == MODEL_ID


def test_the_batch_body_asks_for_strict_structured_output() -> None:
    """AI rule 3: no product decision comes from free text parsed by hand."""
    body = batch.build_body(_request())
    assert body["text"]["format"]["strict"] is True
    assert body["reasoning"]["effort"] == "low"
    # Nothing is retained on OpenAI's side: this is a stranger's résumé.
    assert body["store"] is False


def test_the_resume_never_travels_in_the_instructions() -> None:
    """AI rule 4: candidate content goes in its own `user` message."""
    body = batch.build_body(_request())
    messages = body["input"]

    carrying = [m for m in messages if RESUME_TEXT[:80] in m["content"]]
    assert [m["role"] for m in carrying] == ["user"]
    for message in messages:
        if message["role"] != "user":
            assert RESUME_TEXT[:80] not in message["content"]


def test_the_token_estimate_is_an_overestimate() -> None:
    """Guessing low is the failure that gets a whole batch rejected."""
    items = [batch.BatchItem(custom_id=ROW_A, request=_request())]
    characters = sum(len(m["content"]) for m in batch.build_input(items[0].request))
    estimate = batch.estimate_input_tokens(items)
    # Three characters per token is coarse but never under the real count for
    # ordinary prose, where four is the usual rule of thumb.
    assert estimate == characters // 3
    assert estimate > characters // 4


# --- Submitting -----------------------------------------------------------


def test_submitting_uploads_the_file_then_starts_the_batch(fake) -> None:
    client = fake()
    items = [
        batch.BatchItem(custom_id=ROW_A, request=_request()),
        batch.BatchItem(custom_id=ROW_B, request=_request()),
    ]

    batch_id = batch.submit(items)

    assert batch_id == "batch_test"
    assert client.upload_purpose == "batch"
    assert client.uploaded is not None
    assert len(client.uploaded.decode("utf-8").splitlines()) == 2
    assert client.created_with == {
        "input_file_id": "file_in",
        "endpoint": "/v1/responses",
        "completion_window": "24h",
    }


def test_status_is_read_straight_off_the_batch(fake) -> None:
    fake(status="in_progress")
    assert batch.status("batch_test") == "in_progress"


# --- Collecting -----------------------------------------------------------


def test_results_are_keyed_by_custom_id_not_by_position(fake) -> None:
    """The guide states output order may differ from input order."""
    fake(files={"file_out": OUTPUT_FILE})
    results = {r.custom_id: r for r in batch.collect("batch_test")}

    # The fixture is deliberately stored with B before A.
    assert [r.custom_id for r in batch.collect("batch_test")][:2] == [ROW_B, ROW_A]
    assert results[ROW_A].output is not None
    assert results[ROW_B].output is not None
    assert results[ROW_A].output.criteria[0].criterion_name == "Python"


def test_token_usage_comes_back_for_costing(fake) -> None:
    fake(files={"file_out": OUTPUT_FILE})
    results = {r.custom_id: r for r in batch.collect("batch_test")}

    assert results[ROW_A].input_tokens == 1187
    assert results[ROW_A].output_tokens == 621
    assert results[ROW_B].input_tokens == 1102


def test_a_failed_row_comes_back_with_its_reason_not_dropped(fake) -> None:
    """The regression this file exists for.

    Failed and expired rows are written to `error_file_id`, a *different* file
    from the successful ones. Reading only the output file lost every failure,
    and the scheduler then recorded the useless "missing from batch output"
    instead of what actually went wrong.
    """
    client = fake(
        output_file_id="file_out",
        error_file_id="file_err",
        files={"file_out": OUTPUT_FILE, "file_err": ERROR_FILE},
    )
    results = {r.custom_id: r for r in batch.collect("batch_test")}

    assert client.fetched == ["file_out", "file_err"]
    assert ROW_EXPIRED in results
    assert results[ROW_EXPIRED].output is None
    assert "batch_expired" in (results[ROW_EXPIRED].error or "")
    assert "max_output_tokens" in (results[ROW_REJECTED].error or "")


def test_a_batch_of_nothing_but_failures_still_reports_them(fake) -> None:
    """With no successes there is no output file at all."""
    fake(output_file_id=None, error_file_id="file_err", files={"file_err": ERROR_FILE})
    results = batch.collect("batch_test")

    assert {r.custom_id for r in results} == {ROW_EXPIRED, ROW_REJECTED}
    assert all(r.output is None and r.error for r in results)


def test_a_malformed_row_is_reported_and_does_not_kill_the_batch(fake) -> None:
    fake(files={"file_out": OUTPUT_FILE})
    results = {r.custom_id: r for r in batch.collect("batch_test")}

    assert results[ROW_C].output is None
    assert results[ROW_C].error is not None
    assert results[ROW_C].error.startswith("unparseable:")
    # Its neighbours survived it.
    assert results[ROW_A].output is not None


def test_a_response_with_no_message_is_reported_rather_than_crashing(fake) -> None:
    """All the tokens went to reasoning and nothing was written."""
    fake(files={"file_out": OUTPUT_FILE})
    results = {r.custom_id: r for r in batch.collect("batch_test")}

    assert results[ROW_D].output is None
    assert "no output_text" in (results[ROW_D].error or "")


def test_a_batch_with_neither_file_collects_nothing(fake) -> None:
    fake(output_file_id=None, error_file_id=None)
    assert batch.collect("batch_test") == []


def test_blank_lines_in_a_file_are_skipped(fake) -> None:
    fake(files={"file_out": f"\n{OUTPUT_FILE}\n\n"})
    assert len(batch.collect("batch_test")) == 4


def test_an_error_string_is_truncated(fake) -> None:
    """A runaway message must not become a runaway database row."""
    row = {"custom_id": ROW_A, "response": None, "error": {"message": "x" * 4000}}
    fake(files={"file_out": json.dumps(row)})
    (result,) = batch.collect("batch_test")

    assert result.error is not None
    assert len(result.error) == 500
