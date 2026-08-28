"""Read-only links for people without an account.

The token is the credential here, so these tests are about what it grants, what
it never grants, and how it stops granting it.
"""

import json
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schema import EvaluationOutput
from app.db.models import Application, AuditLog, HumanDecision, ResumeDocument, ShareLink
from app.db.types import DecisionKind
from app.services import sharing
from app.services.evaluation import persist_evaluation
from tests.factories import make_application, make_opening

FIXTURES = Path(__file__).parent / "fixtures"
_FIXTURE = json.loads((FIXTURES / "strong_candidate.json").read_text(encoding="utf-8"))
RESUME_TEXT: str = _FIXTURE["resume_text"]


def _candidate(session: Session, opening: object, email: str, decision: DecisionKind | None):
    application = make_application(session, opening, email)  # type: ignore[arg-type]
    application.resume = ResumeDocument(
        storage_path=f"{application.id}/cv.pdf", visible_text=RESUME_TEXT, total_text=RESUME_TEXT
    )
    session.flush()
    persist_evaluation(session, application, EvaluationOutput.model_validate(_FIXTURE["output"]))
    if decision is not None:
        application.decision = HumanDecision(
            kind=decision, reason="Because.", decided_by="ana@acme.com"
        )
    session.flush()
    return application


def _share(client: TestClient, opening_id: object, **payload: object) -> dict[str, object]:
    body = {"scope": "shortlist", "label": "Hiring manager", "days": 14, **payload}
    response = client.post(f"/api/v1/openings/{opening_id}/share", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- The token ---


def test_only_the_hash_of_the_token_is_stored(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """A dump of this table must grant nobody a view."""
    opening = make_opening(session, slug="share-hash")
    session.commit()
    created = _share(client, opening.id)
    token = str(created["url_path"]).rsplit("/", 1)[1]

    link = session.scalar(select(ShareLink))
    assert link is not None
    assert token not in link.token_hash
    assert link.token_hash == sharing.hash_token(token)


def test_the_token_is_long_and_unguessable(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-entropy")
    session.commit()

    tokens = {str(_share(client, opening.id)["url_path"]).rsplit("/", 1)[1] for _ in range(5)}

    assert len(tokens) == 5
    assert all(len(t) >= 40 for t in tokens)


def test_the_audit_entry_does_not_carry_the_token(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """An audit row that leaks a credential is worse than no audit row."""
    opening = make_opening(session, slug="share-audit")
    session.commit()
    created = _share(client, opening.id)
    token = str(created["url_path"]).rsplit("/", 1)[1]

    log = session.scalar(select(AuditLog).where(AuditLog.action == "share.create"))
    assert log is not None
    assert token not in json.dumps(log.payload)


# --- What it shows ---


def test_a_shortlist_link_shows_only_shortlisted_candidates(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Nobody outside the company should see who was declined."""
    opening = make_opening(session, slug="share-scope")
    kept = _candidate(session, opening, "kept@example.com", DecisionKind.SHORTLIST)
    _candidate(session, opening, "declined@example.com", DecisionKind.REJECT)
    _candidate(session, opening, "undecided@example.com", None)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])

    body = client.get(f"/api/v1{path}").json()

    assert [c["id"] for c in body["candidates"]] == [str(kept.id)]


def test_the_shared_view_hides_contact_details(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """A hiring manager needs the assessment, not the candidate's phone number."""
    opening = make_opening(session, slug="share-pii")
    _candidate(session, opening, "pii@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])

    raw = client.get(f"/api/v1{path}").text

    assert "pii@example.com" not in raw
    candidate = client.get(f"/api/v1{path}").json()["candidates"][0]
    assert "email" not in candidate
    assert "phone" not in candidate
    # But the evidence, which is the point of sharing it, is there.
    assert candidate["criteria"][0]["evidence"]


def test_the_shared_view_is_never_indexed(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-noindex")
    _candidate(session, opening, "idx@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])

    headers = client.get(f"/api/v1{path}").headers

    assert "noindex" in headers["x-robots-tag"]
    assert headers["cache-control"] == "no-store"


def test_a_page_image_is_reachable_only_for_a_visible_candidate(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-pages")
    session.commit()
    from tests.pdfs import make_resume

    client.post(
        "/openings/share-pages/apply",
        data={"full_name": "Ada", "email": "sp@example.com", "consent": "true"},
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
    )
    hidden = session.scalar(select(Application))
    assert hidden is not None
    _candidate(session, opening, "shown@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])
    token = path.rsplit("/", 1)[1]

    # The undecided applicant is not in the link's scope, so neither is their file.
    assert client.get(f"/api/v1/shared/{token}/candidates/{hidden.id}/pages/1").status_code == 404


# --- What it cannot do ---


def test_the_link_cannot_decide_or_reach_the_panel(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-readonly")
    application = _candidate(session, opening, "ro@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])
    client.get(f"/api/v1{path}")  # holding the token changes nothing
    client.cookies.clear()  # and the reader has no session

    assert client.get(f"/api/v1/openings/{opening.id}/applications").status_code == 401
    assert client.get(f"/api/v1/applications/{application.id}").status_code == 401
    assert (
        client.post(
            f"/api/v1/applications/{application.id}/decision",
            json={"kind": "reject", "reason": "no", "decided_by": "x"},
        ).status_code
        == 401
    )


# --- When it stops working ---


def test_an_expired_link_is_refused(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-expired")
    _candidate(session, opening, "exp@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])
    link = session.scalar(select(ShareLink))
    assert link is not None
    link.expires_at = sharing.now() - timedelta(minutes=1)
    session.flush()

    assert client.get(f"/api/v1{path}").status_code == 404


def test_a_revoked_link_stops_working_immediately(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-revoked")
    _candidate(session, opening, "rev@example.com", DecisionKind.SHORTLIST)
    session.commit()
    created = _share(client, opening.id)
    path = str(created["url_path"])
    assert client.get(f"/api/v1{path}").status_code == 200

    assert client.delete(f"/api/v1/share/{created['link']['id']}").status_code == 204

    assert client.get(f"/api/v1{path}").status_code == 404


def test_an_unknown_token_answers_exactly_like_an_expired_one(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Distinguishing the two tells a guesser they found something real."""
    opening = make_opening(session, slug="share-same")
    _candidate(session, opening, "same@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])
    link = session.scalar(select(ShareLink))
    assert link is not None
    link.expires_at = sharing.now() - timedelta(minutes=1)
    session.flush()

    expired = client.get(f"/api/v1{path}")
    unknown = client.get("/api/v1/shared/there-is-no-such-token-at-all-abcdefghij")

    assert expired.status_code == unknown.status_code == 404
    assert expired.json()["detail"] == unknown.json()["detail"]


def test_views_are_counted_but_readers_are_not_identified(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Knowing a link was opened is useful; knowing who opened it is surveillance."""
    opening = make_opening(session, slug="share-count")
    _candidate(session, opening, "cnt@example.com", DecisionKind.SHORTLIST)
    session.commit()
    path = str(_share(client, opening.id)["url_path"])

    for _ in range(3):
        client.get(f"/api/v1{path}")

    link = session.scalar(select(ShareLink))
    assert link is not None
    assert link.view_count == 3
    assert link.last_viewed_at is not None
    assert not any(log.action.startswith("share.view") for log in session.scalars(select(AuditLog)))


def test_creating_and_listing_links_needs_a_session(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="share-auth")
    session.commit()

    assert client.post(f"/api/v1/openings/{opening.id}/share", json={}).status_code == 401
    assert client.get(f"/api/v1/openings/{opening.id}/share").status_code == 401


def test_a_link_lifetime_is_capped(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="share-cap")
    session.commit()

    assert (
        client.post(f"/api/v1/openings/{opening.id}/share", json={"days": 3650}).status_code == 422
    )
