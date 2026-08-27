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
