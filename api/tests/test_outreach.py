"""Closing an opening and writing to candidates.

No test sends a real email: `sender.send` is the seam, and it is stubbed.
"""

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
