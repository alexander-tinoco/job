<h1 align="center">Verbatim</h1>
<p align="center"><b>AI-assisted résumé screening where every score carries the sentence it came from — checked against the document before it is shown.</b></p>

<p align="center">
  <a href="https://github.com/alexander-tinoco/job/actions/workflows/ci.yml"><img src="https://github.com/alexander-tinoco/job/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.14">
  <img src="https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=white" alt="React 19">
  <img src="https://img.shields.io/badge/coverage-94%25%20branch-brightgreen?style=flat-square" alt="Branch coverage 94%">
  <img src="https://img.shields.io/badge/mutants%20killed-614%2F615-brightgreen?style=flat-square" alt="614 of 615 mutants killed">
  <img src="https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker ready">
</p>

Small businesses get two hundred applications and read the first fifty properly. Verbatim reads
all of them and shows its work: a weighted score, the criteria behind it, and for every criterion
the literal sentences from the résumé that justify it. It's a portfolio project, built to
production standards rather than a CRUD demo with an AI theme on top — and the parts that are
**not** proven are stated as plainly as the parts that are.

- **The model never emits the number that ranks anyone.** It scores criteria 0–5; Python applies the rubric weights
- **Every quote is verified** character for character against the résumé, with the offsets shown; an invented one flags the evaluation for a human
- **Four anti-injection layers, none of which trust the model** — a tampered résumé scores identically to its clean twin, measured
- **$0.00031 per résumé**, measured, not estimated: one batched AI call per candidate and arithmetic for everything else
- **Nothing is filtered out automatically.** Declining takes a person, a reason and an audit entry
- OpenTelemetry traces, canonical logs and Prometheus metrics, all off-by-default and free when unconfigured
- **415 Python tests, 15 browser journeys, 94% branch coverage**, property-based tests and mutation testing in CI

## Screenshots

<table>
  <tr>
    <td width="33%"><img src="docs/screenshots/08-ranking.png" alt="The ranking"><br><sub>The ranking. Rows 04 and 05 are the same résumé — one hiding an instruction — and both score 48</sub></td>
    <td width="33%"><img src="docs/screenshots/09-candidate-evidence.png" alt="Evidence"><br><sub>Every criterion with its weight, its rating and the quotes behind it, each with its offsets</sub></td>
    <td width="33%"><img src="docs/screenshots/14-compare.png" alt="Comparison"><br><sub>Two candidates, with the gap attributed to the criteria that carry it</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/11-concealed-layer.png" alt="Concealed layer"><br><sub>Text hidden from human readers, surfaced with the reason it was invisible</sub></td>
    <td><img src="docs/screenshots/18-shared-shortlist.png" alt="Shared shortlist"><br><sub>A read-only link, opened with no session: no email, no phone, nothing that writes</sub></td>
    <td><img src="docs/screenshots/19-trace-waterfall.png" alt="A trace"><br><sub>One panel request in Jaeger, with every query nested under it and timed</sub></td>
  </tr>
</table>

<sub>Every screenshot is taken from the running stack by <a href="docs/capture.mjs"><code>docs/capture.mjs</code></a>. The evaluations are real model output. <a href="docs/ENGINEERING.md#what-it-looks-like">More of them →</a></sub>

## Architecture

```mermaid
flowchart LR
    Applicant(["Applicant"])
    HR(["HR · hiring manager"])
    Web["React panel<br/>+ public application page"]
    API["FastAPI<br/>REST"]
    Ingest["ingest/<br/>PyMuPDF · visible text only"]
    Verify["ai/verify<br/>quote checking · weighted score"]
    PG[("PostgreSQL 16<br/>queue · audit · tsvector")]
    Worker["scheduler<br/>every 6 h · or 50 pending"]
    OpenAI[("OpenAI Batch API<br/>one call per candidate")]
    Obs["OpenTelemetry · Prometheus"]

    Applicant -- "PDF" --> Web
    HR --> Web
    Web -- "same origin" --> API
    API --> Ingest
    Ingest -- "sanitized text" --> PG
    PG -. "pending rows" .-> Worker
    Worker --> OpenAI
    OpenAI -- "strict JSON" --> Verify
    Verify --> PG
    API -. "traces · metrics" .-> Obs
```

**No RAG, no embeddings, no vector database.** Company context and the rubric are text HR writes
when creating the opening, and they go in the prompt. Extracting, sanitizing, splitting and
scoring is Python. The single AI call happens at the very end, and everything around it is
deterministic — which is what makes the anti-injection design possible and the cost a third of a
cent.

<details>
<summary><b>The four anti-injection layers, in one diagram</b></summary>

```mermaid
sequenceDiagram
    participant C as Candidate's PDF
    participant I as ingest/
    participant M as gpt-5.6-luna
    participant P as Python
    participant HR as Panel

    C->>I: "Ignore all previous instructions" in white on white
    Note over I: layer 1 — every span checked for WCAG contrast,<br/>size, render mode, opacity, and occlusion
    I->>M: visible text only, in its own user message
    Note over M: layer 2 — a closed strict schema.<br/>"10/10, hire them" is not representable
    M->>P: {criterion, 0–5, justification, quotes[]}
    Note over P: layer 3 — Python applies the rubric weights.<br/>The model cannot emit the ranking number
    Note over P: layer 4 — every quote must appear verbatim<br/>in the source, or the evaluation is flagged
    P->>HR: score, criteria, quotes with character offsets
```

Measured on the golden set: the tampered résumé scores **48**, exactly what its clean twin
scores. The attack bought nothing, and the reviewer is told it was attempted.
</details>

## Engineering highlights

A few decisions that are probably worth a closer look than the rest.

**The model is not allowed to rank anyone.** `EvaluationOutput` has no overall score field — by
construction, not by convention. The model rates criteria 0–5 and Python computes
`(score / 5) × weight`. A résumé that talks its way into a high criterion score still cannot
rank itself, and because the total is a weighted sum, the gap between two candidates
**decomposes exactly** — which is what lets the comparison screen say where a difference lives
instead of merely that one exists.

**Quote verification carries an offset map, and that map has been wrong.** Quotes are matched
after collapsing whitespace, because extraction rebuilds line breaks from PDF geometry — but the
offsets returned point into the *original* text, because that is what the panel highlights.
Hypothesis found on its first run that `"İ".lower()` is two characters, so a position found in
the lower-cased string ran off the end of a map built from the original: `IndexError` out of
`verify()`, propagating from the batch collector and rolling back **an entire worker tick**. A
Turkish name in a résumé was enough. The counterexample is kept as a named test.

**The Batch API has two result files, and reading one loses every failure.** Successful rows land
in `output_file_id`; failed and expired ones land in `error_file_id` carrying `response: null`.
The collector read only the first, so a failure was dropped and the queue recorded the useless
"missing from batch output" instead of what the API actually said. Found by writing the tests the
audit called for — the module had been at 46% coverage, and the scheduler's own tests mocked it
away entirely.

**Money and secrets fail closed.** The background worker is off unless explicitly enabled, because
a loop that starts by accident spends real money. `/metrics` answers 404 until a token is set.
Sending email is unavailable rather than silently dropped when unconfigured. Secrets are
`SecretStr`, after a pytest assertion printed a live API key into a terminal.

**Throttling counts what succeeded, not what was attempted.** The public application endpoint
takes no session and does real work per call — a 10 MB upload, an inline PyMuPDF pass, a queue
row that becomes a paid model call. Limits are counted per accepted application, so a blocked
caller cannot extend their own lockout by continuing to knock, and they are deliberately loose:
a flood is obvious in the numbers, while a real candidate turned away is invisible.

**One canonical log line per request, and its correlation id *is* the trace id.** A log line and
its trace are the same thing seen from two sides. Handlers add facts with `note(...)` where those
facts are known — the application id, never the candidate — so answering "what happened to that
application?" is one search returning one line, instead of stitching an access log, a handler
message and a stack trace together by timestamp.

**The tests are graded.** Coverage says a line ran, not that anything would have noticed it
behaving differently. Mutation testing changes the code on purpose and checks whether the suite
goes red: 615 mutants, 614 killed. It found two real gaps in fully covered code — dropping
`digest_size=8` changed nothing observable except the size of what is stored, eightfold; and
`lower()` → `upper()` survived because folding both sides preserves equality, *except* that
`"ß".upper()` is `"SS"`, so folding upward would make *Straße* and *Strasse* one document.

<details>
<summary><b>What it costs, measured</b></summary>

| | |
|---|---|
| One résumé, batched | **$0.00031** |
| 500 résumés (one opening) | **$0.16** |
| A client at ~500/month | **≈ $10.31**, hosting included |

`gpt-5.6-luna` at `reasoning.effort: "low"`, chosen on a golden set rather than on tier:
Spearman **+0.976** against the answer key versus **+0.927** for `gpt-5.4-mini`, at 26% of the
cost and with zero unverified quotes in 66 runs. Every figure and two retracted claims are in
[`docs/measurements.md`](docs/measurements.md).
</details>

## Running it

```bash
cp .env.example .env          # then fill in OPENAI_API_KEY
docker compose up -d --build

cd api
printf 'pw\npw\n' | .venv/bin/python -m app.cli create-user you@company.com "Your Name"
.venv/bin/python scripts/seed_demo.py     # ten candidates through the real public endpoint
```

| | |
|---|---|
| Public site | http://localhost:5173 |
| Application page | http://localhost:5173/apply/data-analyst-demo |
| Panel | http://localhost:5173/panel · `demo@acme.com` / `correct-horse-battery` |
| API docs | http://localhost:8000/docs |

Traces need a viewer, and one ships behind a compose profile:

```bash
OTEL_ENDPOINT=http://jaeger:4318/v1/traces docker compose --profile tracing up -d
# then http://localhost:16686
```

Every setting is listed and explained in [`.env.example`](.env.example). **`COOKIE_SECURE=false`
locally** — compose serves plain http, where a Secure cookie is never stored and the panel would
accept your password and then answer 401 to everything after it.

## Tests

```bash
cd api  && .venv/bin/pytest -q --cov     # 415 tests, coverage floor at 93% branch
cd web  && npm run e2e                   # 15 browser journeys against the real stack
cd api  && .venv/bin/mutmut run          # grades the suite; slow, so not in CI
```

Four gates, all enforced in CI and all chosen to fail on a regression rather than on noise:
branch coverage ≥ 93%, cyclomatic complexity ≤ 8, ruff's security rules, and `mypy --strict` over
all of `app/`. Each was proved to bite by deliberately breaking it.

No automated test calls the paid API. Recorded fixtures live in `api/tests/fixtures/`, and
[their README](api/tests/fixtures/README.md) records where each one came from.

## What is not proven

The honest part, and the first thing a reviewer should push on.

**No real opening has run.** The answer key the model is measured against was constructed, not
observed — it shows the system agrees with *a* ranking, not with a hiring manager's. The plan
records this as a permanent limitation rather than a pending task, because those résumés will not
be obtained. That risk is cheap: re-running an entire opening costs sixteen cents, so a rubric
that reads badly can be corrected mid-round.

**One company per deployment.** There is no tenant on `User`, so the panel shows every opening to
everyone who can sign in. That is correct for one company and a leak for two, so creating a second
company is refused with an explanation rather than left as an assumption.

**Scanned résumés are weaker.** A photographed page has no text layer, so the hidden-text defence
cannot apply. Those applications are flagged for manual review rather than quietly scored as if
they had been checked.

## Layout

```
api/            FastAPI · SQLAlchemy 2.0 · Alembic
  app/ai/       the single AI call, its strict schema, quote verification
  app/ingest/   PyMuPDF extraction, hidden-text detection, OCR fallback
  app/services/ scoring, queue, duplicates, sharing, throttling, lifecycle
  app/workers/  the batch scheduler and its loop
  tests/        415 tests, including property-based and migration round-trips
web/            React 19 · Vite · TypeScript strict
  e2e/          15 Playwright journeys against the real stack
docs/           the plan, the measurements, the deck, the screenshots
  ENGINEERING.md   how every part works, and why it works that way
  PLAN-MVP.md      the design and the scope
  measurements.md  every API cost measured, retractions included
  Verbatim.pdf     an 18-page overview to send someone
```
