# Candidate Screening

AI-assisted résumé screening for small businesses. Applications are received through a public
link, parsed deterministically, and scored against a weighted rubric with quoted evidence from
the résumé itself. A person always makes the final call.

Full design: [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md). Working rules: [`CLAUDE.md`](CLAUDE.md).

## Requirements

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Docker (for Postgres)
- Node 20+ (only for the commit hooks)

## Setup

```bash
# Database
docker compose up -d

# Commit hooks
npm install

# API
cd api
uv venv --python 3.14
uv pip install -e ".[dev]"
cp ../.env.example ../.env      # then fill in OPENAI_API_KEY and ADMIN_TOKEN
uv run alembic upgrade head
```

## Running

```bash
cd api
.venv/bin/uvicorn app.main:app --reload    # http://localhost:8000/docs
```

## Authentication

Private endpoints are guarded by an `X-Admin-Token` header compared against `ADMIN_TOKEN`.
This is a placeholder until real auth arrives in Phase 8. It **fails closed**: an unset
`ADMIN_TOKEN` disables every private endpoint rather than leaving the CRUD open.

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" localhost:8000/api/v1/openings
```

The public opening page (`GET /openings/{slug}`) needs no token and never exposes
`company_context` or the rubric — publishing the scoring criteria would tell candidates
exactly what to write.

## Applying

`POST /openings/{slug}/apply` is public — the slug is the invitation. It takes a multipart form
with `full_name`, `email`, `consent`, an optional `phone` and `linkedin_url`, and a `resume`
PDF.

Uploads are validated **while streaming**, not after: the first bytes must match the `%PDF-`
magic number (the `Content-Type` header is supplied by the uploader, so a renamed executable
passes it), and the read aborts past `MAX_UPLOAD_BYTES`. Accepting the whole body first would
mean a 2 GB upload has already filled the disk by the time it is rejected.

Files land in `{UPLOADS_DIR}/{application_id}/{random}.pdf`. The filename is random rather than
derived from the candidate's name, so the path cannot be guessed even by someone who knows the
application id.

There is **no rate limiting** on this endpoint yet. Cloudflare goes in front of the API at
deployment (Phase 11).

## Extraction and sanitization

Runs inline on upload — deterministic, free, and fast, so the panel shows the résumé, its text
and any tampering flags from the moment it arrives. **No model is involved.**

A span of text is treated as hidden from a human when any of these holds:

| Rule | Signal |
|---|---|
| `invisible_render_mode` | PDF text render mode 3 draws nothing |
| `transparent` | opacity below 0.05 |
| `too_small` | font under 4pt |
| `low_contrast` | WCAG contrast under 1.5:1 against the background **under that span** |
| `off_page` | more than half the box lies outside the page |
| `covered` | an opaque shape painted after it, completely over it |

Only `visible_text` is ever sent to the model. `total_text` keeps everything, and the delta is
the evidence shown to HR. Backgrounds are resolved per span, not per page, so dark-on-dark text
inside a navy sidebar is caught while the legible white text beside it is not.

Deterministic injection patterns **flag, they never reject** — a false positive removes a real
person from a hiring process.

### OCR

Scanned résumés have no text layer, so **none of the rules above can protect them**. They are
flagged `ocr_no_hidden_text_detection` and marked for manual review rather than quietly
evaluated as though they had been checked.

OCR needs the Tesseract binary. Without it the file is still accepted and still flagged — the
pipeline degrades, it does not break.

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa
```

## Cost

### What we use

`gpt-5.4-mini` with `reasoning.effort: "low"`, sent through the Batch API. Roughly **$0.0025
per résumé**, about **$1.20 per 500**.

### What we measured

Every model and effort level actually tried, on the same two résumés and the same two-criterion
rubric. Reproduce with `api/scripts/measure_effort.py`; raw output in
`api/tests/fixtures/effort_measurements.json`.

| Résumé | Model | Effort | In | Out | of which reasoning | $ / résumé | Scores |
|---|---|---|---|---|---|---|---|
| clean | gpt-5.4-mini | `none` | 1,045 | 200 | 0 | $0.00168 | Python 4, Postgres 3 |
| clean | gpt-5.4-mini | `low` | 1,045 | 334 | 60 | $0.00229 | Python 4, Postgres 3 |
| clean | gpt-5.4-mini | `medium` (default) | — | ~11,000 | most of it | **~$0.050** | Python 4, Postgres 3 |
| clean | gpt-5.6-luna | `none` | 1,045 | 281 | 0 | **$0.00055** | Python 5, Postgres 3 |
| clean | gpt-5.6-luna | `low` | 1,045 | 324 | 68 | **$0.00060** | Python 5, Postgres 3 |
| injected | gpt-5.4-mini | `none` | 1,076 | 245 | 0 | $0.00191 | Python 4, Postgres 4 |
| injected | gpt-5.4-mini | `low` | 1,076 | 398 | 119 | $0.00260 | Python 4, Postgres 3 |
| injected | gpt-5.4-mini | `medium` (default) | — | ~11,000 | most of it | ~$0.050 | Python 5, Postgres 4 |
| injected | gpt-5.6-luna | `none` | 1,076 | 297 | 0 | $0.00057 | Python 5, Postgres 4 |
| injected | gpt-5.6-luna | `low` | 1,076 | 436 | 165 | $0.00074 | Python 5, Postgres 2 |

`minimal` is rejected on both models with a 400. Supported: `none`, `low`, `medium`, `high`,
`xhigh`.

**Total spent on all measurement so far: about $0.17**, of which ~$0.15 was the first three
calls made before `reasoning.effort` was pinned.

### Three things this settled

**1. Reasoning effort does not change the price, it changes the volume.** The rate per token is
fixed by the model. Reasoning tokens never appear in the response and are **billed as output**,
so an unset effort is expensive with nothing in the response revealing it. Left at the default
`medium`, a résumé cost about 20× more for identical scores. `REASONING_EFFORT` is pinned in
`app/ai/evaluator.py` and guarded by a test.

**2. `gpt-5.6-luna` is roughly 4× cheaper than `gpt-5.4-mini`,** at $0.0006 against $0.0023 per
résumé at `low`. That part is solid: cost is deterministic.

**3. The injection results are not stable between runs, so no conclusion can be drawn from
them yet.** An earlier run of `gpt-5.4-mini` at `none` scored the injected résumé Python 5; the
run in the table above scored it Python 4, from an identical request. Same model, same effort,
same input, different output.

That instability is the finding. It means the earlier observation that `low` "resisted" the
injection was a single sample of a stochastic process, and it cannot support a decision about
either effort or model. Phase 6 measures this against the golden set, where a difference has to
survive twenty résumés before it counts.

Until then: the model stays `gpt-5.4-mini` (changing it is the owner's call), the design assumes
injection still inflates, and the defence rests on layers 1, 3 and 4 — none of which depend on
the model behaving well.

### What the Batch API needs that the synchronous path does not

Batch is not "the same request with a flag". Four differences, all of which Phase 7 must
handle:

1. **No `text_format`.** `client.responses.parse(text_format=Model)` does not exist on the
   batch path. The request body carries a raw JSON Schema under `text.format`.
2. **The Pydantic schema has to be flattened.** `model_json_schema()` emits `$defs` and `$ref`,
   which `strict: true` rejects. Without flattening, the batch path silently loses layer 2 of
   the anti-injection design — in exactly the place production runs. This is a Phase 7
   deliverable with its own acceptance criterion.
3. **A different call sequence.** Build JSONL of `{custom_id, method, url, body}` →
   `files.create(purpose="batch")` → `batches.create(endpoint="/v1/responses")` → poll →
   `files.content(output_file_id)`. Results come back **in any order**; key them by
   `custom_id`, never by position.
4. **An enqueued-token limit per usage tier.** Batch caps how many input tokens may be queued
   at once, and the cap rises with account spend. A 500-résumé batch is far past the lower
   tiers, so the scheduler splits each send into sub-batches.

Batch is 50 % off input and output, reasoning tokens included, since they bill as output.

**Turnaround is not fast, even when tiny.** A three-request batch stayed `in_progress` for over
forty minutes in measurement. The window is 24 h and not configurable. This is why the panel
says "evaluation in progress" and never a time, and why the synchronous "evaluate now" button
exists.

## Tests

Tests run against **real Postgres**, not SQLite: native enums, JSONB and the generated
`tsvector` column do not exist in SQLite, so an in-memory database would let tests pass while
production fails. They create and drop a throwaway `screening_test` database on each run, so
`docker compose up -d` must be running first.

```bash
cd api
.venv/bin/pytest
```

## Checks

```bash
cd api
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy .
```

The `pre-commit` hook runs these three whenever a Python file under `api/` is staged. It checks
but never rewrites — an auto-fix would leave changes unstaged and silently outside the commit.
When it fails, run `.venv/bin/ruff check --fix . && .venv/bin/ruff format .` yourself.

## Migrations

```bash
cd api
.venv/bin/alembic revision --autogenerate -m "what changed"
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade base    # full teardown, enum types included
```

Autogenerate does not emit `DROP TYPE` for native enums. If you add one, drop it explicitly in
the migration's `downgrade()` or the next `upgrade` will fail with "type already exists".

## Layout

| Path | What lives there |
|---|---|
| `api/app/core/` | Config and shared dependencies |
| `api/app/db/` | SQLAlchemy models, session, enums, UUIDv7 keys |
| `api/app/ingest/` | PDF extraction, sanitization, integrity — **no AI** |
| `api/app/ai/` | The single OpenAI call, prompts, quote verification |
| `api/app/workers/` | Queue consumer and batch scheduler |
| `web/` | React panel and public application form |
