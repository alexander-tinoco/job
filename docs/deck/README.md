# The Verbatim deck

`docs/Verbatim.pdf` — fourteen A4 pages for someone deciding whether this MVP is worth their
time. Every cost figure in it was measured against the real API, not estimated.

## Rebuilding it

The stack must be running and seeded, because the screenshots are of the real product with real
evaluations — not mockups.

```bash
docker compose up -d --build
docker compose exec api python -m app.cli create-user demo@acme.com "Ana Ruiz"
cd api && .venv/bin/python scripts/seed_demo.py     # ~11 evaluations, about a cent
```

Then, with a Chromium on disk:

```bash
cd docs/deck
node capture.mjs        <path-to-chrome>   # screens 01–09
node capture2.mjs       <path-to-chrome>   # screens 10–13
node recapture-form.mjs <path-to-chrome>   # screen 02, clipped to the form
node topdf.mjs          <path-to-chrome>   # renders Verbatim.pdf
```

`puppeteer-core` is used rather than `puppeteer` so it reuses a Chromium already on the machine
instead of downloading a second one. The document is plain HTML and CSS printed by the browser,
in the product's own type and palette.

## What is captured

| | |
|---|---|
| 01–04 | The applicant: the opening on a phone, the form, the confirmation, the receipt |
| | Screen 02 is clipped to the form itself rather than captured full-page: a tall mobile capture scaled into a column shows the header and loses the fields, which is the part worth seeing |
| 05–07 | Sign-in, the ranked list, search by surname |
| 08–09 | Findings with cited evidence, and the raking light linking a quote to its position |
| 10 | The concealed layer — the tampered résumé scoring the same as its clean twin |
| 11 | The document rendered server-side as images |
| 12–13 | A recorded decision, and focused reading |
