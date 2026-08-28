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

## Running the whole thing

```bash
cp .env.example .env            # then fill in OPENAI_API_KEY and ADMIN_TOKEN
docker compose up -d --build
```

| | |
|---|---|
| Public site | http://localhost:5173 |
| Application page | http://localhost:5173/apply/{slug} |
| Panel | http://localhost:5173/panel |
| API docs | http://localhost:8000/docs |

### Where the panel lives

The panel's URL segment is set per deployment with `VITE_PANEL_PATH` (and `PANEL_PATH` on the
API), it is never linked from the public site, and `robots.txt` disallows it.

**That is hygiene, not a security control, and it must not be treated as one.** A URL leaks
through browser history, `Referer` headers, bookmarks and any chat someone pastes it into. What
protects the panel is the sign-in: Argon2, a server-side session, an `HttpOnly` cookie and a
lockout. Changing the path keeps the admin surface out of sight and out of search results;
it stops nobody who is actually looking.

The application page is deliberately **not** obscured. That link gets posted on LinkedIn: it has
to be clean and readable, because a candidate who sees a scrambled URL assumes phishing.

nginx serves the panel and proxies `/api` and `/openings` to the API, so the browser sees a
single origin: no CORS, and the admin token never crosses an origin boundary.

**Compose reads the repository's `.env` automatically**, so `OPENAI_API_KEY` and `ADMIN_TOKEN`
reach the containers without being written into `docker-compose.yml`. Override one for a single
run with `ADMIN_TOKEN=... docker compose up -d`.

### Something to look at

```bash
# A user to sign in with
docker compose exec api python -m app.cli create-user demo@acme.com "Ana Ruiz"

# Ten candidates, uploaded through the real public endpoint and evaluated
cd api && .venv/bin/python scripts/seed_demo.py
```

The seed uploads the ten golden-set résumés and evaluates them — about a cent. It includes the
tampered copy, which is the interesting row: **it scores identically to its clean twin**,
because the hidden text was stripped before anything was evaluated.

#### Walk the applicant's path

The seed publishes one opening. Its public page is:

**http://localhost:5173/apply/data-analyst-demo**

This is the hiring company's page, not Verbatim's: Mercadis leads, and Verbatim signs once at
the foot. The opening is written the way a company writes one — what the team does, what the
role owns, what they are looking for, and how they hire.

The applicant never sees the rubric and never learns a score. Sending requires the consent box,
which starts unchecked — GDPR art. 22, not a UI flourish — and then asks for confirmation,
because an application cannot be unsent and a candidate gets one. The page that follows says
the application is in, that a person will read it, that nothing is filtered out automatically,
and that they can close the tab.

Apply with any PDF, then open the panel. Your application appears **at the top of the list**,
marked *awaiting examination* and with no score: extraction is deterministic and runs on upload,
so the résumé, its text and its integrity flags are there immediately, while the score waits for
the next batch. **Examine now** on the candidate's page runs that one synchronously instead —
seconds, and about $0.0006.

To see the part that shows the product best, upload the tampered file the golden set already
carries:

```
api/tests/golden/pdfs/ibarra_injected.pdf
```

It arrives flagged **concealed text**, and its page shows what the eye cannot see — the hidden
instruction, its reason, its contrast ratio against the background and its page number — beside
a score computed from the visible text alone.

#### Local demo credentials

| | |
|---|---|
| Email | `demo@acme.com` |
| Password | `correct-horse-battery` |

**These are for the local compose stack and nothing else.** They are written here because the
stack is worthless to look at without a way in, and they open a database of invented candidates
on `localhost`. A deployment creates its own account with `app.cli create-user` and a real
password; nothing in this repository ships a default login.

## Local development

```bash
docker compose up -d db         # just the database
cd api
uv venv --python 3.14
uv pip install -e ".[dev]"
uv run alembic upgrade head
.venv/bin/uvicorn app.main:app --reload

cd ../web && npm install && npm run dev
```

### Commit hooks

```bash
npm install                     # at the repository root
```

## Authentication

Email and password, with a server-side session in an `HttpOnly` cookie.

```bash
cd api
.venv/bin/python -m app.cli create-user you@company.com "Your Name"
```

### The choices, and why

| Decision | Reason |
|---|---|
| **Argon2id**, explicit parameters | Memory-hard: a leaked hash costs an attacker RAM per guess, not just cycles. Parameters are pinned so a library default cannot silently weaken every stored password |
| **Server-side sessions**, not a self-contained token | Revocable. Logging out, disabling an account or a suspected theft take effect on the next request instead of waiting for an expiry |
| **Only the token's hash is stored** | A dump of the sessions table hands nobody a working session |
| **`HttpOnly` cookie**, not `localStorage` | No script on the page can read it. An XSS can act while the page is open but cannot steal a credential to use later from elsewhere |
| **`SameSite=Strict`** | Another origin cannot make the browser act as this user, which removes the CSRF class here |
| **`Secure`** unless `COOKIE_SECURE=false` | Off only for local http |
| **A new token on every sign-in** | Session fixation: a value planted beforehand never becomes the authenticated one |
| **Idle and absolute deadlines** (8 h / 24 h) | A session ends at whichever comes first |
| **Identical answer for unknown email and wrong password** | Different answers turn the login form into an account directory |
| **A dummy hash when no user matches** | Otherwise the response time answers "does this email exist?" |
| **5 failures per email, 20 per address, 15-minute window** | The lockout holds even once the password is right, so guessing on the last attempt buys nothing |
| **8-character minimum, no composition rules** | NIST SP 800-63B. Forced rules produce `Password1!` |
| **Sign-in and sign-out to `AuditLog`** | — |

The public opening page (`GET /openings/{slug}`) needs no session and never exposes
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

## Closing an opening and writing to candidates

Close the opening, draft, read, send. Four steps, and the last one is a person.

```
POST /api/v1/openings/{id}/close        the opening stops accepting applications
POST /api/v1/openings/{id}/outreach     drafts one email per decided candidate
PATCH /api/v1/outreach/{id}             rewrite it
POST /api/v1/outreach/{id}/send         the only call that sends anything
```

**Drafting requires the opening to be closed.** Drafting mid-round invites declining someone the
round would have reconsidered.

**The emails come from templates**, versioned in `app/outreach/templates/` beside the evaluator's
prompts, with merge fields filled by Python. **Not written by a model** — and not for cost, since
one call per shortlisted candidate is five or ten per opening. A generated email invents, and
"we were impressed by your work on X" is exactly the sentence a model produces and exactly the
sentence that is wrong when X is not in the résumé. It goes out over the client's name to
somebody who did not get the job.

The decline says the decision was made by a person and that the résumé is deleted in six months
unless they ask sooner. That is the product's position and what keeps it out of GDPR art. 22.

**Sending takes a name and records it**, along with the template version, in `AuditLog`. The
audit entry carries no recipient address and no body: it records that a person approved a send,
not the contents of somebody's rejection. A sent message can no longer be edited, and sending
twice is refused.

With `RESEND_API_KEY` unset, sending answers **503** rather than accepting the approval and
dropping the message. A product that silently swallows rejection emails is worse than one that
cannot send them.

## Comparing candidates

A score answers "is this one any good". The decision is "this one or that one", and two totals
side by side answer that no better than one does.

```
GET /api/v1/openings/{id}/compare?ids=<a>&ids=<b>[&ids=<c>]
```

Because the overall score is a weighted sum, **the gap decomposes exactly**: each criterion
contributes `(score / 5) × weight`, so the per-criterion differences add up to the difference in
the totals, and the screen can say how many points of the gap each row is worth. A test asserts
that identity rather than trusting it.

The headline sentence names the smallest set of criteria carrying more than half the gap — one
when one criterion really is the story, more when the difference is genuinely spread out.
Naming a fixed two would be a claim the numbers do not support.

Three columns is the maximum. Only examined candidates can be compared: inventing zeros for one
still in the queue would read as a judgement nobody made. Candidates from different openings are
refused too — different rubrics, different weights, so the rows would not mean the same thing.

## Sharing a shortlist

Whoever screens is rarely whoever decides. Without a way to show a hiring manager the shortlist,
the only option is handing them a password.

```
POST   /api/v1/openings/{id}/share   mint a link; the token is returned once
GET    /api/v1/openings/{id}/share   list the links and their view counts
DELETE /api/v1/share/{id}            revoke one immediately
GET    /api/v1/shared/{token}        the read-only view — no session
```

**Here the token is the credential**, unlike the panel's path. So it is 256 bits of randomness,
only its SHA-256 is stored, it expires (14 days by default, 90 maximum), and it can be revoked.
A dump of `share_links` grants nobody a view.

What the link shows: shortlisted candidates, their scores, the criteria and the quoted evidence,
and the résumé. What it never shows: **email, phone, LinkedIn, everyone who was declined, the
reviewer's reason, and the audit trail.** There is no control on that page that writes anything.

An unknown token and an expired one answer identically — distinguishing them would tell a
guesser they had found something real. Views are counted; readers are not identified, because
knowing a link was opened is useful and knowing who opened it is surveillance nobody asked for.
Every response carries `X-Robots-Tag: noindex`.

## Retention, access and erasure

The application page tells a candidate their résumé is deleted six months after the opening
closes and that they can ask for it sooner. These are the endpoints that make those true.

```
POST /api/v1/retention/sweep            delete what is past the window
GET  /api/v1/data-subject/{email}       everything held about one person
POST /api/v1/data-subject/erase         delete it
GET  /api/v1/openings/{id}/export.csv   the opening's results
GET  /api/v1/audit                      who did what
```

**Retention also runs on the worker's tick**, not only when someone calls the endpoint. A
promise on a public page cannot depend on a person remembering to press a button.

The window is measured **from the opening closing**, not from the application arriving: someone
who applied on day one and someone who applied on the last day belong to the same round and are
kept for the same period.

**Files are deleted before rows.** A row without its file is a recoverable inconsistency; a file
without its row is personal data nobody can find, list or delete.

**Erasure keeps the audit trail, anonymised.** The actor becomes `erased` and the entry is
marked, but the record survives — deleting it would erase the proof that a human made each
decision, which is the record the same regulation requires. The erasure entry itself carries no
email: writing down who asked to be forgotten would defeat the exercise.

**The CSV neutralises formulas.** A candidate chooses their own name, a name can start with `=`,
and Excel and Sheets will run it. Cells beginning with `=`, `+`, `-` or `@` are prefixed with a
quote.

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

### The model decision — decided by measurement, not by tier

**We use `gpt-5.6-luna` at `reasoning.effort: "low"`.** Changed from `gpt-5.4-mini` on
2026-08-27.

`gpt-5.6-luna` — 1,050,000 token context, 128,000 max output, knowledge cutoff 2026-02-16,
efforts `none` through `max`.

**Luna is OpenAI's volume tier — the nano-equivalent of this generation.** An earlier version of
this file said it sat "in the flagship family rather than the mini line" and called the switch a
move up in capability. That was wrong: OpenAI's own model page puts Luna at the nano tier and
its guidance is "use Luna for volume, not for depth". The decision was not made on tier and does
not depend on it.

#### What it was decided on

Ten synthetic data-analyst candidates across ten résumé layouts, three runs each per model:

| Metric | `gpt-5.6-luna` | `gpt-5.4-mini` |
|---|---|---|
| Spearman ρ against the answer key | **+0.976** | +0.927 |
| Mean standard deviation across runs | **2.07** | 2.23 |
| Unverified quotes, 33 runs each | 0 | 0 |
| Bottom two candidates separated correctly | **yes** | no |
| Cost per résumé | **$0.00087** | $0.00335 |

`mini` ranked the accountant with no SQL — who fails the mandatory criterion — *below* a graduate
with no experience at all, and scored them within 0.3 points of each other. Luna put them at 2.7
and 1.3. That is the behaviour the product needs.

#### Where luna sits against the rest of its family

| Benchmark | sol | terra | **luna** |
|---|---|---|---|
| Intelligence Index (max effort) | 59 | 55 | **51** |
| Agents' Last Exam | 53.6 | 50.4 | **50.3** |
| Terminal-Bench 2.1 | 88.8 % | 87.4 % | **84.7 %** |
| Coding Agent Index | 80 | 77.4 | **74.6** |
| SWE-bench Pro | 64.6 % | 63.4 % | **62.7 %** |
| GPQA Diamond | > 92 % | > 92 % | **> 92 %** |
| **MRCR long-context recall** | 91.5 % | 89.6 % | **41.3 %** |
| Cost per task | $1.04 | $0.55 | **$0.21** |

Luna is within a few points of the tier above it on almost everything. **None of those benchmarks
measure this task**, though — they are agentic, coding and science-QA evaluations. They are
context, not evidence. The golden set above is the evidence.

#### The one benchmark that matters to this architecture

**MRCR is 41.3 % against terra's 89.6 %.** It measures recall from a long input, and it is the
only place luna falls off a cliff.

It does not bite today: prompts are around 1,000 tokens. But this design deliberately has **no
retrieval** — the company context goes in the prompt (plan §4), which makes prompt size the
dimension that grows as a client accumulates context. We have chosen the model weakest at exactly
that.

The tripwire is written down in plan §5.1.4: **if the assembled prompt passes 15,000 tokens,
re-run `scripts/compare_models.py` against `gpt-5.6-terra` before shipping it.** At terra's price
the evaluation would cost about $0.005 per résumé — still under three cents for a hundred
candidates, so this is a quality decision, not a budget one.

#### Still unproven

The golden set's answer key is constructed, not observed. It measures agreement with a ranking
the author invented. Phase 6 repeats the same experiment against real résumés with a human
ordering, and that run is the one that decides.

### What the Batch API needs that the synchronous path does not

Batch is not "the same request with a flag". Four differences, all of which Phase 7 must handle:

1. **No `text_format`.** `client.responses.parse(text_format=Model)` does not exist on the batch
   path. The request body carries a raw JSON Schema under `text.format`.
2. **The Pydantic schema has to be hardened.** `model_json_schema()` omits
   `additionalProperties: false`, and strict mode refuses a schema without it:
   *"In context=(), 'additionalProperties' is required to be supplied and to be false"*.
   `app/ai/batch_schema.py` adds it to every object, root and `$defs` alike, and makes every
   property required. Without that the batch path silently loses layer 2 of the anti-injection
   design — in exactly the place production runs.

   An earlier version of this file said `$defs`/`$ref` had to be flattened away. **That was
   wrong**: strict mode accepts them, verified against the API. The real gap was much smaller.
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

## Background processing

Applications are queued for evaluation as soon as extraction produces usable text. The scheduler
runs two separate jobs (see plan §4.1):

- **Send** at 00:00, 06:00, 12:00 and 18:00, or immediately once 50 applications are waiting.
- **Collect** hourly, because a batch can finish anywhere inside its 24-hour window.

The queue lives in Postgres and is claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, which is
what makes two workers safe without a locking protocol — and what keeps Redis and Celery out of
the deployment.

The **enqueued-token limit is discovered at runtime, not read from a dashboard**. The scheduler
starts from a working budget, and when the API rejects a send for exceeding the limit it halves
the budget and retries next tick. That stays correct whatever usage tier the account is on, and
survives the account changing tier.

A row is retried up to three times. After that it is marked failed and its application moves to
`error` state — visible in the panel, because a candidate whose evaluation failed still needs to
be seen rather than silently dropped.

**The worker is off by default.** `WORKER_ENABLED=true` switches it on; anything else leaves it
stopped. A loop that starts by accident spends real money.

## The HR panel

React + Vite in `web/`. The design world is **The Examiner's Bench** — see `DESIGN.md` for the
palette laws, the type system and the signature interaction; `PRODUCT.md` holds product truth.

Ranked exhibits on the left, the document under examination on the right.

```bash
cd web
npm install
npm run dev          # proxies /api to localhost:8000
```

### What it shows, and why in that shape

**Unscored candidates are listed, not hidden.** Extraction is deterministic and runs on upload,
so the résumé, its text and any tampering flags exist from the moment the application arrives.
Only the score waits for a batch. The row says "Evaluation in progress" and **never a time** —
the batch window is 24 h and not configurable.

**The résumé is shown two ways.** The transcript is what the model actually read, with quoted
passages highlighted; the document register shows the pages **rendered server-side as PNGs**.
Images, not an embedded PDF: the file came from a stranger and PDF viewers execute scripts.

**Evidence is highlighted from stored offsets, not re-searched.** Verification already located
each quote against the exact string the panel renders; searching for it again in the browser
could highlight a different occurrence. A quote that could not be verified is shown struck out
in red rather than dropped, so the reviewer sees that the model claimed something the résumé
does not contain.

**Candidate risks and system flags appear in separate boxes.** `risks` are the model's
observations about the person. `review_flags` are our own verification's objections — an
unfound quote means *our evaluation* has a problem, not the candidate. Shown together they
would invite exactly the wrong reading.

**The list collapses.** Reviewing one application is a reading task, and the ranking beside it
is a distraction once the choice is made. Selecting a candidate always opens their page at the
top; landing halfway down the previous one is how a reviewer misses the summary.

**A tampered résumé is shown, not suppressed.** Its hidden text appears as evidence with the
reason and page, and the score beside it is computed from the visible text only.

**Every decision needs a reason and an author**, and both go to `AuditLog` alongside the model's
score — the disagreement between human and model is the most valuable data the product produces.
The decision never overwrites the evaluation.

### Sign-in and session behaviour

Every credential failure answers **“Email or password incorrect.”** — the same words for a
wrong password, a disabled account and an email nobody has. Anything more specific turns the
form into a way to find out who has an account. The one exception is the lockout, which says
so: telling a throttled person their password is wrong would have them retry for fifteen
minutes, and it reveals nothing, since the throttle counts per address as well as per email.

The password field has a visibility toggle, off by default: the eye is crossed out while the
password is hidden and open once it is readable, so the icon shows the current state rather than
the action. Hiding what someone types defends against a shoulder, not an attacker, and it causes
more failed sign-ins than it prevents.

Signing out asks first, and both the control and its confirmation are oxide — the palette's stop
colour. A review session is long, and losing your place to a misplaced click is worse than one
extra keystroke.

### Search cannot be injected

Every value reaches Postgres as a bound parameter through SQLAlchemy expressions; the only raw
SQL in the codebase is `SELECT 1` in the readiness probe, with no input at all. Tests fire
`' OR 1=1 --` and `'; DROP TABLE applications; --` at the search endpoint and assert the tables
survive.

Separately, `%` and `_` are escaped before they reach `ILIKE`. Not an injection defence — a
bound parameter was never injectable — but a search for `%` would otherwise match every
candidate in the opening, and `a_a` would match “Ada”. The user typed characters, not a pattern.

### Security notes

The original PDF is offered as a download and **never rendered inline**: it was uploaded by a
stranger and PDF viewers execute JavaScript, so inline rendering on the panel's origin would be
XSS with an HR session attached. The API forces `Content-Disposition: attachment`, `nosniff` and
a sandbox CSP. Résumé text is rendered as text, never as markup.

**Authentication is a placeholder and a weak one.** A single shared `X-Admin-Token`, kept in
`localStorage`: no users, no expiry, no rotation, readable by any script on the page. Acceptable
for a one-company-per-deployment MVP; **not acceptable before a real client**. Real auth is
owed before deployment.

## Deployment

```
api/Dockerfile        python:3.14-slim + tesseract, non-root, migrations on start
web/Dockerfile        node build → nginx, proxies /api so there is one origin
docker-compose.yml    db + api + web, api gated on the database being healthy
railway.toml          builder, health check, restart policy
.github/workflows/    api: lint, types, migration up/down/up, tests on real Postgres
                      web: types and build
                      images: both Dockerfiles must still assemble
                      commits: conventional messages on pull requests
```

`alembic upgrade head` runs as part of the container's start command. It is idempotent, so an
up-to-date database is a no-op, and no deploy needs a manual step.

The image runs as uid 10001, not root: uploaded résumés are untrusted input and PyMuPDF parses
them in this process.

### Health versus readiness

Two probes, deliberately different:

| Endpoint | Checks | Purpose |
|---|---|---|
| `/health` | nothing, always cheap | Liveness. Stays 200 with Postgres down |
| `/ready` | `SELECT 1` | Readiness. Returns 503 when the database is unreachable |

A liveness probe that queries the database restarts the app whenever the database blips. A
readiness probe that does not is useless, because the platform keeps routing traffic to an
instance that can do nothing. Railway is pointed at `/ready`.

### CI

The workflow runs lint, `mypy`, a full `alembic upgrade → downgrade → upgrade` cycle and the
test suite against a real Postgres service container. `OPENAI_API_KEY` is deliberately empty:
**no CI job may reach the API**, and every test uses recorded fixtures.

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

`tests/test_migrations.py` enforces this: it runs the full up → down → up cycle against a
throwaway database and asserts no enum type survives a downgrade. That test exists because this
note alone did not stop the defect shipping a second time.

## Layout

| Path | What lives there |
|---|---|
| `api/app/core/` | Config and shared dependencies |
| `api/app/db/` | SQLAlchemy models, session, enums, UUIDv7 keys |
| `api/app/ingest/` | PDF extraction, sanitization, integrity — **no AI** |
| `api/app/ai/` | The single OpenAI call, prompts, quote verification |
| `api/app/workers/` | Queue consumer and batch scheduler |
| `web/` | React panel and public application form |
