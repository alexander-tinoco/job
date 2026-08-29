"""Deliver an approved email through Resend.

Uses the REST endpoint over stdlib HTTP rather than adding a client library for
one POST. Fails closed: with no API key configured, sending raises instead of
pretending to succeed — a product that silently drops rejection emails is worse
than one that cannot send them.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.core.config import get_settings

ENDPOINT = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 20


class SendingUnavailableError(RuntimeError):
    """No provider is configured, so nothing can be sent."""


class SendFailedError(RuntimeError):
    """The provider rejected the message."""


@dataclass(frozen=True)
class Delivery:
    provider_message_id: str


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.resend_api_key.get_secret_value() and settings.outreach_from)


def send(to: str, subject: str, body: str) -> Delivery:
    settings = get_settings()
    if not is_configured():
        raise SendingUnavailableError(
            "Email sending is not configured. Set RESEND_API_KEY and OUTREACH_FROM."
        )

    payload = json.dumps(
        {
            "from": settings.outreach_from,
            "to": [to],
            "subject": subject,
            # Plain text on purpose: these are short personal messages, and HTML
            # mail from an unfamiliar sender is what spam filters look at hardest.
            "text": body,
        }
    ).encode("utf-8")

    request = urllib.request.Request(ENDPOINT, data=payload, method="POST")
    request.add_header("Authorization", f"Bearer {settings.resend_api_key.get_secret_value()}")
    request.add_header("Content-Type", "application/json")

    try:
        # noqa S310: the URL is the module constant above, never anything a
        # caller supplies, so no scheme can be smuggled in.
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            answer = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        # The provider's body explains the refusal; the key is in a header we
        # never echo, so this is safe to store and show.
        raise SendFailedError(f"{exc.code}: {exc.read().decode()[:300]}") from exc
    except OSError as exc:
        raise SendFailedError(f"Could not reach the mail provider: {exc}") from exc

    return Delivery(provider_message_id=str(answer.get("id", "")))
