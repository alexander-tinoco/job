"""Closing an opening and writing to candidates.

No test sends a real email: `sender.send` is the seam, and it is stubbed.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, OutreachDraft
from app.db.types import DecisionKind, OpeningStatus, OutreachKind, OutreachState
from app.outreach import render, sender
from tests.factories import make_application, make_opening


def _decided(session: Session, opening: object, email: str, kind: DecisionKind):
    from app.db.models import HumanDecision

    application = make_application(session, opening, email)  # type: ignore[arg-type]
    application.decision = HumanDecision(kind=kind, reason="Because.", decided_by="hr@acme.com")
    session.flush()
    return application


@pytest.fixture
def delivered(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Capture what would have been sent instead of sending it."""
    seen: list[tuple[str, str, str]] = []

    def fake(to: str, subject: str, body: str) -> sender.Delivery:
        seen.append((to, subject, body))
        return sender.Delivery(provider_message_id="msg_test")

    monkeypatch.setattr("app.outreach.sender.send", fake)
    return seen


# --- Templates ---


def test_the_templates_render_with_the_candidate_and_role() -> None:
    merge = render.Merge(
        first_name="Ada", role="Data Analyst", company="Mercadis", sender_name="Ana Ruiz"
    )

    for kind in (OutreachKind.INVITE, OutreachKind.DECLINE):
        rendered = render.render(kind, merge)
        assert "Ada" in rendered.body
        assert "Data Analyst" in rendered.subject
        assert "Mercadis" in rendered.body
        assert "{" not in rendered.body, "an unfilled merge field would ship a brace"


def test_the_decline_says_a_person_decided() -> None:
    """The product's position, and what keeps it out of GDPR art. 22."""
    body = render.render(
        OutreachKind.DECLINE,
        render.Merge(first_name="Ada", role="R", company="C", sender_name="S"),
    ).body

    assert "made by a person" in body
    assert "six months" in body


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [("Ada Lovelace", "Ada"), ("  Elena  Vargas ", "Elena"), ("", "there")],
)
def test_the_greeting_takes_the_first_word_only(full_name: str, expected: str) -> None:
    assert render.first_name(full_name) == expected


# --- Drafting ---


def test_drafting_needs_the_opening_closed(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Drafting mid-round invites declining someone the round would reconsider."""
    opening = make_opening(session, slug="out-open")
    _decided(session, opening, "a@example.com", DecisionKind.REJECT)
    session.commit()

    response = client.post(f"/api/v1/openings/{opening.id}/outreach")

    assert response.status_code == 409
    assert "Close the opening" in response.text


def test_drafting_covers_every_decided_candidate_and_skips_the_rest(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="out-draft")
    _decided(session, opening, "yes@example.com", DecisionKind.SHORTLIST)
    _decided(session, opening, "no@example.com", DecisionKind.REJECT)
    make_application(session, opening, "undecided@example.com")
    opening.status = OpeningStatus.CLOSED
    session.commit()

    body = client.post(f"/api/v1/openings/{opening.id}/outreach").json()

    kinds = sorted(draft["kind"] for draft in body)
    assert kinds == [OutreachKind.DECLINE, OutreachKind.INVITE]
    assert all(draft["state"] == OutreachState.DRAFT for draft in body)
    assert all(draft["sent_at"] is None for draft in body)


def test_drafting_twice_replaces_rather_than_duplicates(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="out-twice")
    _decided(session, opening, "twice@example.com", DecisionKind.SHORTLIST)
    opening.status = OpeningStatus.CLOSED
    session.commit()

    client.post(f"/api/v1/openings/{opening.id}/outreach")
    client.post(f"/api/v1/openings/{opening.id}/outreach")

    assert len(list(session.scalars(select(OutreachDraft)))) == 1


# --- Editing ---


def test_a_draft_can_be_rewritten_before_it_goes(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="out-edit")
    _decided(session, opening, "edit@example.com", DecisionKind.SHORTLIST)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]

    response = client.patch(
        f"/api/v1/outreach/{draft['id']}",
        json={"subject": "Let us talk", "body": "Hi Ada, are you free Thursday?"},
    )

    assert response.status_code == 200
    assert response.json()["subject"] == "Let us talk"


# --- Sending ---


def test_nothing_is_sent_until_a_person_sends_it(
    client: TestClient, session: Session, auth: dict[str, str], delivered: list[object]
) -> None:
    opening = make_opening(session, slug="out-nosend")
    _decided(session, opening, "quiet@example.com", DecisionKind.REJECT)
    opening.status = OpeningStatus.CLOSED
    session.commit()

    client.post(f"/api/v1/openings/{opening.id}/outreach")

    assert delivered == [], "drafting must not deliver anything"


def test_sending_records_who_approved_it(
    client: TestClient, session: Session, auth: dict[str, str], delivered: list[object]
) -> None:
    opening = make_opening(session, slug="out-send")
    _decided(session, opening, "send@example.com", DecisionKind.SHORTLIST)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]

    response = client.post(
        f"/api/v1/outreach/{draft['id']}/send", json={"approved_by": "ana@acme.com"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == OutreachState.SENT
    assert body["approved_by"] == "ana@acme.com"
    assert len(delivered) == 1

    log = session.scalar(select(AuditLog).where(AuditLog.action == "outreach.invite"))
    assert log is not None
    # The audit records that a person approved a send, not the contents of
    # somebody's rejection.
    assert "body" not in log.payload
    assert "email" not in log.payload


def test_sending_without_a_name_is_refused(
    client: TestClient, session: Session, auth: dict[str, str], delivered: list[object]
) -> None:
    opening = make_opening(session, slug="out-noname")
    _decided(session, opening, "noname@example.com", DecisionKind.REJECT)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]

    response = client.post(f"/api/v1/outreach/{draft['id']}/send", json={"approved_by": ""})

    assert response.status_code == 422
    assert delivered == []


def test_sending_twice_is_refused(
    client: TestClient, session: Session, auth: dict[str, str], delivered: list[object]
) -> None:
    opening = make_opening(session, slug="out-double")
    _decided(session, opening, "double@example.com", DecisionKind.REJECT)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]
    payload = {"approved_by": "ana@acme.com"}

    first = client.post(f"/api/v1/outreach/{draft['id']}/send", json=payload)
    second = client.post(f"/api/v1/outreach/{draft['id']}/send", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(delivered) == 1


def test_a_sent_message_can_no_longer_be_edited(
    client: TestClient, session: Session, auth: dict[str, str], delivered: list[object]
) -> None:
    opening = make_opening(session, slug="out-frozen")
    _decided(session, opening, "frozen@example.com", DecisionKind.REJECT)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]
    client.post(f"/api/v1/outreach/{draft['id']}/send", json={"approved_by": "ana@acme.com"})

    response = client.patch(f"/api/v1/outreach/{draft['id']}", json={"subject": "x", "body": "y"})

    assert response.status_code == 409


def test_a_provider_failure_is_recorded_and_the_draft_survives(
    client: TestClient, session: Session, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    opening = make_opening(session, slug="out-fail")
    _decided(session, opening, "fail@example.com", DecisionKind.REJECT)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]

    def boom(to: str, subject: str, body: str) -> object:
        raise sender.SendFailedError("422: domain not verified")

    monkeypatch.setattr("app.outreach.sender.send", boom)
    response = client.post(
        f"/api/v1/outreach/{draft['id']}/send", json={"approved_by": "ana@acme.com"}
    )

    assert response.status_code == 502
    stored = session.scalar(select(OutreachDraft))
    assert stored is not None
    assert stored.state is OutreachState.FAILED
    assert "domain not verified" in (stored.last_error or "")


def test_sending_is_unavailable_rather_than_silent_when_unconfigured(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """A product that quietly drops rejection emails is worse than one that cannot send."""
    opening = make_opening(session, slug="out-unconfigured")
    _decided(session, opening, "unconf@example.com", DecisionKind.REJECT)
    opening.status = OpeningStatus.CLOSED
    session.commit()
    draft = client.post(f"/api/v1/openings/{opening.id}/outreach").json()[0]

    # No RESEND_API_KEY in the test environment.
    response = client.post(
        f"/api/v1/outreach/{draft['id']}/send", json={"approved_by": "ana@acme.com"}
    )

    assert response.status_code == 503
    assert "not configured" in response.text


def test_outreach_requires_a_session(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="out-auth")
    session.commit()

    assert client.get(f"/api/v1/openings/{opening.id}/outreach").status_code == 401
    assert client.post(f"/api/v1/openings/{opening.id}/outreach").status_code == 401


# --- The provider call itself ---
#
# `sender.send` was the least covered part of outreach: everything above it is
# tested against a stubbed sender, so the request actually put on the wire — and
# the header carrying the key — was never looked at.


def _resend(
    monkeypatch: pytest.MonkeyPatch, reply: bytes = b'{"id":"msg_123"}'
) -> dict[str, object]:
    """Capture the request instead of making it."""
    from app.core.config import get_settings

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("OUTREACH_FROM", "hr@acme.com")
    get_settings.cache_clear()

    seen: dict[str, object] = {}

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return reply

    def fake_urlopen(request: object, timeout: float = 0) -> _Response:
        seen["url"] = request.full_url  # type: ignore[attr-defined]
        seen["headers"] = dict(request.header_items())  # type: ignore[attr-defined]
        seen["body"] = json.loads(request.data)  # type: ignore[attr-defined]
        return _Response()

    monkeypatch.setattr("app.outreach.sender.urllib.request.urlopen", fake_urlopen)
    return seen


def test_the_message_goes_out_as_plain_text_from_the_configured_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _resend(monkeypatch)
    delivery = sender.send("ada@example.com", "About your application", "Hello Ada,")

    assert delivery.provider_message_id == "msg_123"
    body = seen["body"]
    assert body["from"] == "hr@acme.com"  # type: ignore[index]
    assert body["to"] == ["ada@example.com"]  # type: ignore[index]
    assert body["text"] == "Hello Ada,"  # type: ignore[index]
    # HTML mail from an unfamiliar sender is what spam filters look at hardest.
    assert "html" not in body  # type: ignore[operator]


def test_the_key_travels_in_a_header_and_nowhere_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _resend(monkeypatch)
    sender.send("ada@example.com", "Subject", "Body")

    headers = {k.lower(): v for k, v in seen["headers"].items()}  # type: ignore[union-attr]
    assert headers["authorization"] == "Bearer re_test_key"
    assert "re_test_key" not in json.dumps(seen["body"])
    assert "re_test_key" not in str(seen["url"])


def test_a_refusal_from_the_provider_is_reported_with_its_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import urllib.error

    _resend(monkeypatch)

    def refuse(request: object, timeout: float = 0) -> object:
        raise urllib.error.HTTPError(
            "https://api.resend.com/emails",
            422,
            "Unprocessable",
            {},
            io.BytesIO(b'{"message":"domain not verified"}'),
        )

    monkeypatch.setattr("app.outreach.sender.urllib.request.urlopen", refuse)

    with pytest.raises(sender.SendFailedError) as caught:
        sender.send("ada@example.com", "Subject", "Body")

    assert "422" in str(caught.value)
    assert "domain not verified" in str(caught.value)


def test_an_unreachable_provider_is_reported_rather_than_raising_a_socket_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _resend(monkeypatch)

    def unreachable(request: object, timeout: float = 0) -> object:
        raise OSError("Name or service not known")

    monkeypatch.setattr("app.outreach.sender.urllib.request.urlopen", unreachable)

    with pytest.raises(sender.SendFailedError, match="Could not reach"):
        sender.send("ada@example.com", "Subject", "Body")


def test_a_reply_without_an_id_still_returns_a_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draft is recorded as sent either way; the id is for tracing, not truth."""
    _resend(monkeypatch, reply=b"")
    assert sender.send("ada@example.com", "Subject", "Body").provider_message_id == ""


def test_sending_unconfigured_raises_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()

    def never(*_: object, **__: object) -> object:
        raise AssertionError("no request should be made")

    monkeypatch.setattr("app.outreach.sender.urllib.request.urlopen", never)

    with pytest.raises(sender.SendingUnavailableError):
        sender.send("ada@example.com", "Subject", "Body")
