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

Everything below is measured, not estimated. Reproduce with the scripts in `api/scripts/`;
raw output in `api/tests/fixtures/`.

### Every model and effort we tried

Same two résumés, same two-criterion rubric, ~1,050 input tokens each.

| Model | Effort | Output tokens | of which reasoning | $ / résumé | Clean CV scores |
|---|---|---|---|---|---|
| gpt-5.4-mini | `none` | 200 | 0 | $0.00168 | Python 4, Postgres 3 |
| gpt-5.4-mini | `low` **(ours)** | 334 | 60 | $0.00229 | Python 4, Postgres 3 |
| gpt-5.4-mini | `medium` (default) | 737 | 516 | $0.00410 | Python 5, Postgres 3 |
| gpt-5.6-luna | `none` | 281 | 0 | $0.00055 | Python 5, Postgres 3 |
| gpt-5.6-luna | `low` | 324 | 68 | $0.00060 | Python 5, Postgres 3 |
| gpt-5.6-luna | `medium` | 388 / 400 / 519 | 133 / 130 / 253 | $0.00068–0.00083 | 4,3 · 4,3 · 4,2 |

`minimal` is rejected on both models with a 400. Supported: `none`, `low`, `medium`, `high`,
`xhigh`. Batch is 50 % off input and output; reasoning tokens bill as output, so they are
discounted too.

**Total spent on measurement: about $0.20.**

### A correction

An earlier version of this file claimed the default `medium` effort cost "roughly 20×" `low`.
**That was wrong.** It came from dividing an observed $0.15 spend by three calls, never from a
measurement. Measured directly, `gpt-5.4-mini` at `medium` costs **1.79×** `low` — real, but
nothing like 20×. The $0.15 is not accounted for by these numbers and remains unexplained; the
per-request breakdown in the OpenAI dashboard would settle it.

Pinning `reasoning.effort` is still right — being explicit about a parameter that silently
changes cost is worth doing, and 1.79× is worth having — but it is not the emergency the earlier
note described.

### What reasoning effort actually does

It does not change the price per token; it changes how many output tokens get burned. Reasoning
tokens never appear in the response and are **billed as output**, which is what makes the cost
move without anything visible changing.

The size of that effect is per model, and the difference is large: at `medium`, `gpt-5.4-mini`
spent 516 reasoning tokens while `gpt-5.6-luna` spent 130–253 for the same work. "Medium" is not
a comparable setting across models.

### The model decision — settled on cost, open on quality

**We use `gpt-5.6-luna` at `reasoning.effort: "low"`.** Changed from `gpt-5.4-mini` on
2026-08-27.

| Model | Effort | $ / résumé | vs. previous |
|---|---|---|---|
| gpt-5.4-mini | `low` (previous) | $0.00229 | — |
| **gpt-5.6-luna** | **`low` (current)** | **$0.00062** | **27 %** |

`luna` sits in the flagship family rather than the mini line, so this is a move up in
capability tier at a quarter of the price — the earlier "do not drop to nano" reasoning does not
apply here.

### Why not more reasoning, given the savings

The obvious idea is to spend the savings on a higher effort and come out ahead on both. It was
measured, three identical runs per level, and it does not work.

| Effort | Clean CV (Python, Postgres) × 3 runs | Stable? | $ / résumé |
|---|---|---|---|
| `none` | (5,4) (5,3) (5,3) | no | $0.00051 |
| **`low`** | **(5,3) (5,3) (4,3)** | no | **$0.00062** |
| `medium` | (4,3) (4,3) (4,2) | no | $0.00073 |
| `high` | (5,2) (5,2) (5,1) | no | $0.00096 |
| `xhigh` | (5,2) (4,2) (5,1) | no | $0.00174 |

Two things came out of this:

**More reasoning did not reduce variance.** Every level, including `xhigh`, gave different
scores across identical requests. The instability is not something effort buys away.

**More reasoning systematically lowered a criterion.** Postgres reads 3,3,3 at `low` and 2,2,1
at `high` — a trend, not noise. Higher effort changes the calibration rather than sharpening it,
and there is no ground truth here to say which reading is right.

`low` is therefore the pick on its merits, not just its price: it is the most consistent level
measured, and its Postgres reading of 3 is the one `gpt-5.4-mini` also gave. At `none` the model
once returned only one of the two criteria, which `verify()` correctly flagged for human review
— another reason not to go lower.

### What is still unproven

Nothing here shows luna is *better* than mini, only cheaper and differently calibrated: luna
reads Python as 5 where mini read 4, on the same résumé, and neither has been checked against a
human ranking. A ±1 swing appears between identical runs, so any quality claim smaller than that
is unsupportable from this data.

Phase 6 ranks both models against 15–20 real résumés with a human ordering. If luna loses there,
the change reverts — the cost saving does not outrank a worse screen.

### What the Batch API needs that the synchronous path does not

Batch is not "the same request with a flag". Four differences, all of which Phase 7 must handle:

1. **No `text_format`.** `client.responses.parse(text_format=Model)` does not exist on the batch
   path. The request body carries a raw JSON Schema under `text.format`.
2. **The Pydantic schema has to be flattened.** `model_json_schema()` emits `$defs` and `$ref`,
   which `strict: true` rejects. Without flattening, the batch path silently loses layer 2 of
   the anti-injection design — in exactly the place production runs. Phase 7 deliverable with
   its own acceptance criterion.
3. **A different call sequence.** Build JSONL of `{custom_id, method, url, body}` →
   `files.create(purpose="batch")` → `batches.create(endpoint="/v1/responses")` → poll →
   `files.content(output_file_id)`. Results come back **in any order**; key them by `custom_id`,
   never by position.
4. **An enqueued-token limit per usage tier.** Batch caps how many input tokens may be queued at
   once, and the cap rises with account spend. A 500-résumé batch is far past the lower tiers,
   so the scheduler splits each send into sub-batches.

**Turnaround is not fast, even when tiny.** A three-request batch stayed `in_progress` for over
forty minutes in measurement. The window is 24 h and not configurable. This is why the panel says
"evaluation in progress" and never a time, and why the synchronous "evaluate now" button exists.

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
