"""The HR panel API."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schema import EvaluationOutput
from app.db.models import Application, AuditLog, ResumeDocument
from app.db.types import ApplicationState, IntegrityVerdict
from app.services.evaluation import persist_evaluation
from tests.factories import make_application, make_opening
from tests.pdfs import PAYLOAD, make_resume

FIXTURES = Path(__file__).parent / "fixtures"
_FIXTURE = json.loads((FIXTURES / "strong_candidate.json").read_text(encoding="utf-8"))
# The résumé the recorded response actually quotes. Pairing the response with a
# different text would make every quote unverifiable and test nothing.
RESUME_TEXT: str = _FIXTURE["resume_text"]


def _output() -> EvaluationOutput:
    return EvaluationOutput.model_validate(_FIXTURE["output"])


def _evaluated(session: Session, opening_id: object, email: str, text: str = RESUME_TEXT):
    from app.db.models import JobOpening

    opening = session.get(JobOpening, opening_id)
    assert opening is not None
    application = make_application(session, opening, email)
    application.resume = ResumeDocument(
        storage_path=f"{application.id}/cv.pdf", visible_text=text, total_text=text
    )
    session.flush()
    persist_evaluation(session, application, _output())
    application.state = ApplicationState.EVALUATED
    session.flush()
    return application


def test_the_ranking_is_ordered_by_score(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="panel-rank")
    _evaluated(session, opening.id, "a@example.com")
    _evaluated(session, opening.id, "b@example.com")
    session.commit()

    body = client.get(f"/api/v1/openings/{opening.id}/applications", headers=auth).json()

    scores = [item["overall_score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)
    assert body["total"] == 2
    assert body["evaluated"] == 2


def test_an_unscored_candidate_still_appears_with_its_flags(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """The panel must never look empty while a batch is in flight (plan §4.1)."""
    opening = make_opening(session, slug="panel-pending")
    scored = _evaluated(session, opening.id, "scored@example.com")
    waiting = make_application(session, opening, "waiting@example.com")
    waiting.resume = ResumeDocument(storage_path=f"{waiting.id}/cv.pdf", visible_text="text")
    waiting.state = ApplicationState.EXTRACTED
    session.commit()

    items = client.get(f"/api/v1/openings/{opening.id}/applications", headers=auth).json()["items"]

    by_id = {item["id"]: item for item in items}
    assert by_id[str(scored.id)]["overall_score"] is not None
    assert by_id[str(waiting.id)]["overall_score"] is None
    assert by_id[str(waiting.id)]["state"] == ApplicationState.EXTRACTED
    # Scored first, unscored after.
    assert items[0]["id"] == str(scored.id)


def test_the_detail_carries_evidence_offsets_into_the_resume_text(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="panel-detail")
    application = _evaluated(session, opening.id, "detail@example.com")
    session.commit()

    body = client.get(f"/api/v1/applications/{application.id}", headers=auth).json()

    assert body["resume_text"] == RESUME_TEXT
    quotes = [q for c in body["criteria"] for q in c["evidence"] if q["found"]]
    assert quotes, "the fixture should quote the résumé"
    for quote in quotes:
        # The offsets must select exactly the quoted words in the text we return.
        selected = body["resume_text"][quote["start"] : quote["end"]]
        assert selected.replace("\n", " ") == quote["quote"].replace("\n", " ")


def test_candidate_risks_and_system_flags_are_kept_apart(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """A candidate with an unfound quote does not have a problem; our evaluation does."""
    opening = make_opening(session, slug="panel-flags")
    application = _evaluated(session, opening.id, "flags@example.com", text="Nothing relevant.")
    session.commit()

    body = client.get(f"/api/v1/applications/{application.id}", headers=auth).json()

    assert body["needs_human_review"] is True
    assert any("not found verbatim" in flag for flag in body["review_flags"])
    assert all("not found verbatim" not in risk for risk in body["risks"])


def test_the_detail_shows_hidden_text_as_evidence(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    make_opening(session, slug="panel-tampered")
    session.commit()
    client.post(
        "/openings/panel-tampered/apply",
        data={"full_name": "Ada", "email": "t@example.com", "consent": "true"},
        files={"resume": ("cv.pdf", make_resume(hidden=PAYLOAD), "application/pdf")},
    )
    application = session.scalar(select(Application))
    assert application is not None

    body = client.get(f"/api/v1/applications/{application.id}", headers=auth).json()

    assert body["integrity"]["verdict"] == IntegrityVerdict.TAMPERED
    assert PAYLOAD in body["integrity"]["hidden_spans"][0]["text"]
    # The payload is evidence, never part of what anyone evaluates.
    assert PAYLOAD not in body["resume_text"]


def test_search_finds_a_candidate_by_words_in_the_resume(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="panel-search")
    match = _evaluated(
        session, opening.id, "match@example.com", text="Migrated a monolith to services."
    )
    _evaluated(session, opening.id, "other@example.com", text="Ran payroll in Excel.")
    session.commit()

    body = client.get(
        f"/api/v1/openings/{opening.id}/search", params={"q": "monolith"}, headers=auth
    ).json()

    assert [hit["application_id"] for hit in body["hits"]] == [str(match.id)]
    assert "monolith" in body["hits"][0]["excerpt"]


def test_search_does_not_reach_hidden_text(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """The index is over visible_text, so a payload is not searchable either."""
    opening = make_opening(session, slug="panel-search-hidden")
    session.commit()
    client.post(
        "/openings/panel-search-hidden/apply",
        data={"full_name": "Ada", "email": "sh@example.com", "consent": "true"},
        files={
            "resume": ("cv.pdf", make_resume(hidden="SECRETPAYLOAD unicorn"), "application/pdf")
        },
    )

    body = client.get(
        f"/api/v1/openings/{opening.id}/search", params={"q": "unicorn"}, headers=auth
    ).json()

    assert body["hits"] == []


def test_the_resume_is_served_as_a_download_never_inline(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """An uploaded PDF rendered inline is XSS with an HR session attached."""
    make_opening(session, slug="panel-pdf")
    session.commit()
    client.post(
        "/openings/panel-pdf/apply",
        data={"full_name": "Ada", "email": "pdf@example.com", "consent": "true"},
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
    )
    application = session.scalar(select(Application))
    assert application is not None

    response = client.get(f"/api/v1/applications/{application.id}/resume", headers=auth)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.content.startswith(b"%PDF-")


def test_a_decision_is_recorded_with_its_reason_and_author(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="panel-decide")
    application = _evaluated(session, opening.id, "decide@example.com")
    session.commit()

    response = client.post(
        f"/api/v1/applications/{application.id}/decision",
        json={"kind": "shortlist", "reason": "Best Python depth", "decided_by": "hr@acme.com"},
        headers=auth,
    )

    assert response.status_code == 201
    log = session.scalar(select(AuditLog).where(AuditLog.action == "decision.shortlist"))
    assert log is not None
    assert log.payload["reason"] == "Best Python depth"
    # The disagreement between human and model is the data worth keeping.
    assert log.payload["model_score"] is not None


def test_the_decision_does_not_overwrite_the_evaluation(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="panel-coexist")
    application = _evaluated(session, opening.id, "coexist@example.com")
    session.commit()
    before = application.evaluation.overall_score  # type: ignore[union-attr]

    client.post(
        f"/api/v1/applications/{application.id}/decision",
        json={"kind": "reject", "reason": "Not a fit", "decided_by": "hr@acme.com"},
        headers=auth,
    )

    assert application.evaluation is not None
    assert application.evaluation.overall_score == before
    assert application.decision is not None


def test_deciding_twice_is_refused(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="panel-twice")
    application = _evaluated(session, opening.id, "twice@example.com")
    session.commit()
    payload = {"kind": "reject", "reason": "No", "decided_by": "hr@acme.com"}

    first = client.post(
        f"/api/v1/applications/{application.id}/decision", json=payload, headers=auth
    )
    second = client.post(
        f"/api/v1/applications/{application.id}/decision", json=payload, headers=auth
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_a_decision_needs_a_reason(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Every human decision is recorded with its reason (plan §8)."""
    opening = make_opening(session, slug="panel-noreason")
    application = _evaluated(session, opening.id, "noreason@example.com")
    session.commit()

    response = client.post(
        f"/api/v1/applications/{application.id}/decision",
        json={"kind": "reject", "reason": "", "decided_by": "hr@acme.com"},
        headers=auth,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/openings/{opening}/applications",
        "/api/v1/openings/{opening}/search?q=python",
        "/api/v1/applications/{application}",
        "/api/v1/applications/{application}/resume",
    ],
)
def test_every_panel_endpoint_requires_the_token(
    client: TestClient, session: Session, path: str
) -> None:
    opening = make_opening(session, slug="panel-auth")
    application = _evaluated(session, opening.id, "auth@example.com")
    session.commit()

    url = path.format(opening=opening.id, application=application.id)
    assert client.get(url).status_code == 401
