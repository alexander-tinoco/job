# Documentation

| | |
|---|---|
| [`PLAN-MVP.md`](PLAN-MVP.md) | The design, revision 5. Source of truth for the MVP's scope |
| [`measurements.md`](measurements.md) | Every API cost measured, including the claims that were retracted |
| [`Verbatim.pdf`](Verbatim.pdf) | An 18-page overview to send someone: the product, the economics, the risks |
| [`decisions/`](decisions) | Short ADRs for structural choices |
| `screenshots/` | Every image in the README and the deck |

## Rebuilding the screenshots and the PDF

Nothing here is a mockup. The stack has to be up, seeded and — for the tracing shots — running
with the tracing profile and `OTEL_ENDPOINT` set.

```bash
COOKIE_SECURE=false OTEL_ENDPOINT=http://jaeger:4318/v1/traces \
  docker compose --profile tracing up -d --build

cd api
printf 'correct-horse-battery\ncorrect-horse-battery\n' \
  | .venv/bin/python -m app.cli create-user demo@acme.com "Demo"
.venv/bin/python scripts/seed_demo.py          # uploads and evaluates
                                               # (offline: scripts/seed_evaluations.py)

cd ../docs
npm install
node capture.mjs        # writes screenshots/
node deck/topdf.mjs     # writes Verbatim.pdf
```

`capture.mjs` sends its own application and erases it again on the way out, so the demo is left
as it was found. `topdf.mjs` refuses to write a PDF if any image failed to load — a broken one
prints as blank space and is very easy to miss in eighteen pages.

The evaluations behind the panel screenshots are **real model output**. `seed_evaluations.py`
exists for CI, where there is no key; what it writes is scores recorded from real runs with text
assembled from the résumés, and it says so at the top of the file. It must never be screenshotted
as though it were the model's.
