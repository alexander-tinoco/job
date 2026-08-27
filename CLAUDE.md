# CLAUDE.md — Working rules

## Language

**Everything in this project is written in English**: code, comments, commit messages,
documentation, identifiers, database columns, API fields, UI copy and prompts. No exceptions.
Conversation with me can be in Spanish; the repository cannot.

## Project

MVP for AI-assisted candidate screening, aimed at small businesses. The full plan is in
`docs/PLAN-MVP.md` — **read it before proposing anything**. It is the source of truth for
scope: if something is not in there, it does not get built until the plan says so.

Stack: Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 16 (no extensions) · React/Vite in
`web/`. AI: OpenAI `gpt-5.4-mini` via the Batch API. **No RAG, no embeddings, no pgvector** —
evaluation context lives in the prompt (§4 of the plan).

---

## Working framework: phases with sequential roles

We work in **a single terminal**. No subagents are spawned. I play the roles myself, in turn,
within the same session. Every phase runs this full cycle and ends in a commit and a push.

```
  1. ARCHITECT   → proposes the phase design
                   ╠═══ HUMAN GATE 1 ═══╣  ← you authorize
  2. DEVELOPER   → implements exactly what was approved
  3. TESTER      → writes and runs the tests
  4. REVIEWER    → reviews the full diff
                   ╠═══ HUMAN GATE 2 ═══╣  ← you approve
  5. INTEGRATOR  → conventional commit + push
```

### 1. Architect
Before touching a single file:
- What the phase delivers, in one sentence.
- Files created or modified, one line each.
- Contracts: public function signatures, Pydantic schemas, endpoints, tables.
- Non-obvious decisions and why (if structural, it becomes a short ADR in `docs/decisions/`).
- Acceptance criteria: what test proves the phase is done.
- What this phase explicitly does **not** do, when there is room for confusion.

**Writes no code.** Ends by requesting authorization and stops.

### Human gate 1
Wait for an answer. Do not interpret one: "ok", "go ahead", "dale" is a yes. Silence is not.
If you ask for something different from what was proposed, the architect revises and asks again.

### 2. Developer
Implements **what was approved, no more and no less**. If something the architect did not
foresee comes up mid-way:
- An implementation detail → resolve it and mention it when done.
- A contract change, a new dependency, or a file not on the list → **stop and ask**. Do not
  slip it in.

Forbidden in this role: refactoring code unrelated to the phase, fixing something else "while
we're here", adding unrequested features, creating documentation nobody agreed on.

### 3. Tester
- Tests for the phase's acceptance criteria, plus edge cases that matter.
- Run `pytest`, `ruff check` and `mypy`, and **report the real output**. If something fails, say
  it fails and fix it; do not dress it up or leave it out.
- No test calls the OpenAI API for real. Use recorded fixtures in `api/tests/fixtures/`.

### 4. Reviewer
Go through the full diff against this checklist:
- Does it do exactly what gate 1 approved?
- Is any candidate content entering via `system` or via instructions? (see §AI rules)
- Secrets, keys, `.env`, or PII in logs or in the diff?
- Complexity that isn't needed? Premature abstraction?
- Error handling at the edges: user input, corrupt PDF, API down, DB down?
- Do the tests check behaviour, or just cover lines?

Findings get fixed before gate 2.

### Human gate 2
Present a diff summary (`git diff --stat` plus what changed and why) and wait for approval.

### 5. Integrator
`git add` the phase's work, conventional commit, `git push`. **One commit per phase.**
Then propose the next phase and return to the architect role — without starting it.

---

## Gate rules

- **Never** skip a gate, however trivial the phase looks.
- **Never** commit or push without gate 2 approval.
- If I just say "continue", that advances **one** role, not the whole phase.
- If a phase goes wrong and the work should be discarded, say so plainly and propose returning
  to the architect. Do not pile up debt to "fix later".

## Phase size

One complete vertical capability that works end to end. As a guide:
**3–8 files touched, 150–400 net lines.**

- If the architect estimates it will overshoot → **split the phase and say so before gate 1**.
- If it comes in far under (one file, 30 lines) → merge it with the next one.

The goal is calm, visible progress: every push should leave the project in a state you can show
and talk about.

---

## Commits

Conventional format, enforced by commitlint in the `commit-msg` hook:

```
<type>(<scope>): <imperative description, lowercase, no trailing period>
```

**Title only.** No body, no footers, no `Co-Authored-By`, no session links. If a change needs
explanation, it belongs in the code or in `docs/`, not in the commit message.

**Authorship: there is never a co-author other than you.** You are the commit author, full stop.

**Types:** `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `build` · `ci` · `perf` · `style`

**Scopes:** `api` · `db` · `ingest` · `ai` · `web` · `auth` · `infra` · `docs`

Examples:
```
feat(ingest): detect hidden text in pdfs with pymupdf
feat(ai): evaluate candidates with structured output and quoted evidence
feat(ai): process openings in batches via the batch api
chore(infra): add husky and commitlint
```

### Hooks (Phase 0)
| Hook | What runs |
|---|---|
| `pre-commit` | `ruff check`, `ruff format --check` and `mypy` over `api/`, only when a Python file under `api/` is staged. Always via `api/.venv/bin/*`, never the PATH — otherwise the hook silently validates with whatever version the machine has installed |
| `commit-msg` | `commitlint` — type, scope, lowercase subject, and **title only** (`body-empty`, `footer-empty`) |

The hook checks but never rewrites: an auto-fix would leave changes unstaged and silently
outside the commit. When it fails, run `ruff check --fix . && ruff format .` in `api/` yourself.
`pytest` is not in the hook — the tester role runs it in every phase, so no commit reaches
gate 2 without it, and the hook stays fast.

Never `--no-verify`. If a hook gets in the way, fix the hook — don't bypass it.

---

## Code rules

- Python 3.14. Types on every public signature. `mypy --strict` in `app/ai/` and `app/ingest/`.
- No `Any` at boundaries (endpoints, schemas, public return types).
- `ruff` for linting and formatting. No personal config: whatever `pyproject.toml` says.
- Pydantic v2 for anything crossing a boundary (HTTP or the OpenAI API).
- SQLAlchemy 2.0 modern style (`Mapped[...]`, `mapped_column`). No 1.x idioms.
- Migrations **always** through Alembic. Never a hand-written `CREATE TABLE`.
- Comments: only for non-obvious *why*. No comments restating the code.
- Write code that looks like the code already there. If the neighbouring file does something a
  certain way, do it the same way even if you'd prefer another.

---

## AI rules (non-negotiable)

The principle behind all of them: **no AI until the last step.** The pipeline is deterministic
except for one call per candidate. If you find yourself proposing another per-candidate call,
stop and justify it at gate 1.

1. **One AI call per candidate.** No profiling pass, no injection classifier, no orchestrator,
   no model routing. Everything the product needs comes out of that call's schema.
   *One documented exception:* drafting a rubric from a job description, which runs **once per
   opening, not per candidate** (§4.2 of the plan).
2. **Model: `gpt-5.4-mini`.** Do not drop to `nano` for cost — injection resistance scales with
   capability and the saving is ~$1 per opening. Do not move up without my decision.
3. **Always strict structured output**: JSON Schema with `strict: true`. No product decision
   comes from free text parsed by hand.
4. **Candidate content never goes in the `developer`/`system` message**, nor interpolated into
   the instruction template. It goes in its own `user` message.
5. **The model never emits the number that orders the ranking.** It scores criteria 0–5; Python
   computes the overall score from the rubric weights.
6. **Every `evidence` quote is verified** against the sanitized text before being shown. If it
   is not there verbatim, the evaluation is flagged for human review.
7. **One candidate per context.** Never two résumés in the same call.
8. **Prompts live in files** under `app/ai/prompts/*.md`, versioned. Never long literals in the
   code. Every `Evaluation` stores `prompt_version` and `model_id`.
9. **Batch API** for processing an opening. The synchronous path exists only for development and
   the "evaluate now" button.
10. **Extracting, sanitizing, splitting and scoring is Python.** Proposing AI for something an
    algorithm solves is a design error, not a shortcut.
11. **No RAG, embeddings or vector search.** Company context and the rubric are text HR writes
    when creating the opening, and they go in the prompt. Panel search is Postgres `tsvector`.
    Proposing vector retrieval is scope creep.
12. No automated test calls the real API: recorded fixtures in `api/tests/fixtures/`.

Before writing code that calls the OpenAI API, check its current documentation. Do not write
calls from memory: model names and parameters change.

---

## Security and personal data

- `.env` is never committed. `.env.example` is, with fake values.
- No PII (names, emails, phone numbers, résumé text) in logs. Log the `application_id`.
- Uploaded résumés are stored under unguessable names, outside any statically served path.
- The output schema does not model age, gender, nationality, photo or marital status, and the
  evaluator prompt forbids inferring them. See §8 of the plan.
- Every human decision is recorded in `AuditLog` with its reason.

---

## What NOT to do without asking me

- Install a dependency the architect did not list at gate 1.
- Change model or provider.
- Add a second per-candidate AI call to the pipeline.
- Introduce embeddings, pgvector or any form of vector retrieval.
- Add a new infrastructure dependency (Redis, Celery, an external queue). The queue lives in
  Postgres and that is what keeps the deployment at ~$10/month.
- Touch migrations that have already been applied.
- `git push --force`, rewrite history, or commit during an unapproved phase.
- Extend MVP scope with anything from the plan's "Out" list, even if it's ten minutes of work.
- Create documentation, changelogs or READMEs nobody agreed on.
