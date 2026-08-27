"""The single entry point to the OpenAI API.

Everything that talks to a model goes through here so there is one place that
knows the model id, the timeout and where the key comes from.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings

# Changed from gpt-5.4-mini on 2026-08-27 after measurement: luna costs 27% as
# much per résumé and sits in the flagship family rather than the mini line, so
# the earlier "do not drop to nano" reasoning does not apply — this is a move up
# in capability tier, not down. Quality against a human ranking is still
# unverified and is Phase 6's job (docs/measurements.md).
MODEL_ID = "gpt-5.6-luna"

# Long enough for a slow response, short enough that a stuck request does not
# hold a worker for minutes.
REQUEST_TIMEOUT_SECONDS = 120.0


class MissingApiKeyError(RuntimeError):
    """No OPENAI_API_KEY is configured."""


@lru_cache
def get_client() -> OpenAI:
    key = get_settings().openai_api_key
    if not key:
        raise MissingApiKeyError("OPENAI_API_KEY is not set. Add it to .env; see .env.example.")
    return OpenAI(api_key=key, timeout=REQUEST_TIMEOUT_SECONDS)
