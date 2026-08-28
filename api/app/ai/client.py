"""The single entry point to the OpenAI API.

Everything that talks to a model goes through here so there is one place that
knows the model id, the timeout and where the key comes from.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings

# Changed from gpt-5.4-mini on 2026-08-27, decided by measurement rather than by
# tier: on a ten-layout golden set luna ranked closer to the answer key than mini
# (Spearman +0.976 vs +0.927), was marginally more stable, separated the bottom of
# the field correctly where mini did not, and costs 26% as much.
#
# Luna is OpenAI's volume tier — the nano-equivalent of this generation, not a
# step up. An earlier comment here claimed the opposite; that was wrong. The
# decision stands on the measurement, not on where the model sits in the lineup.
#
# Known weakness: MRCR long-context recall is 41.3% against terra's 89.6%. Prompts
# are ~1,000 tokens today so it does not bite, but this design puts the company
# context in the prompt rather than retrieving it (plan §4), so prompt size is the
# dimension that grows. See the tripwire in docs/PLAN-MVP.md §5.1.4.
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
