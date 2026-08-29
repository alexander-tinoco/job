# Recorded fixtures

No automated test calls the OpenAI API (AI rule 12). Everything a test needs about
a real response lives here.

| File | What it is | Where the shape came from |
|---|---|---|
| `strong_candidate.json`, `weak_candidate.json`, `injected_candidate.json` | Golden résumés with the evaluation they produced | Recorded from real synchronous runs by `scripts/record_fixtures.py` |
| `luna_low.json`, `luna_medium.json`, `luna_high.json`, `mini_medium.json` | The same résumé under different models and reasoning efforts, with token counts and cost | Recorded from real runs by `scripts/measure_effort.py` and `scripts/compare_models.py` |
| `effort_measurements.json` | The effort sweep behind §5.1 of the plan | `scripts/measure_effort.py` |
| `batch_output.jsonl` | A finished batch's **output** file | Envelope from the Batch API guide; the `usage` block matches what `scripts/measure_batch.py` read off a real completed batch. Evaluation bodies are the recorded golden ones |
| `batch_error.jsonl` | The same batch's **error** file | Batch API guide: a failed or expired row carries `response: null` and an `error` object |

## Why the batch fixtures are two files

The Batch API writes successful rows to `output_file_id` and failed or expired
rows to `error_file_id`. They are separate files, and a collector that reads only
the first one silently loses every failure. Keeping both here is what makes that
testable.

The output file is deliberately **out of input order**: the guide states the
output line order may not match the input, so anything keyed by position is
wrong by construction.
