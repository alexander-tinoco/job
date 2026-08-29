"""Yes/no facts an applicant states about themselves.

The plan rules out a pre-filter that rejects candidates, so most of what these
tests pin down is the *absence* of consequences: an answer that does not match
still gets an application, an evaluation and a place in the ranking. What it
gets is a note.
"""

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Application, JobOpening, JobQueue, ScreeningQuestion
from app.db.types import ApplicationState
from tests.factories import make_opening
from tests.pdfs import make_resume

FORM = {"full_name": "Ada Lovelace", "email": "ada@example.com", "consent": "true"}


def _ask(session: Session, opening: JobOpening, *questions: tuple[str, bool]) -> None:
    opening.screening_questions = [
        ScreeningQuestion(text=text, expected_answer=expected, position=index)
        for index, (text, expected) in enumerate(questions, start=1)
    ]
    session.flush()


def _apply(client: TestClient, slug: str, **overrides: object) -> object:
    return client.post(
        f"/openings/{slug}/apply",
        data={**FORM, **overrides},
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
    )


# --- What the applicant is shown ---


def test_the_public_form_never_reveals_the_answer_being_looked_for(
    client: TestClient, session: Session
) -> None:
    """Otherwise the question stops being about a fact and becomes a form to pass."""
    opening = make_opening(session, slug="scr-public")
    _ask(session, opening, ("Do you have the right to work in Spain?", True))
    session.commit()

    body = client.get(f"/openings/{opening.slug}").json()

    assert [q["text"] for q in body["screening_questions"]] == [
        "Do you have the right to work in Spain?"
    ]
    serialised = json.dumps(body)
    assert "expected_answer" not in serialised
    assert set(body["screening_questions"][0]) == {"id", "text"}


def test_an_opening_without_questions_publishes_an_empty_list(
    client: TestClient, session: Session
) -> None:
    opening = make_opening(session, slug="scr-none")
    session.commit()

    assert client.get(f"/openings/{opening.slug}").json()["screening_questions"] == []


# --- What answering does, and does not, do ---


def test_an_unmet_requirement_still_produces_a_full_application(
    client: TestClient, session: Session
) -> None:
    """The whole point: no rejection, no hiding, no missing evaluation."""
    opening = make_opening(session, slug="scr-unmet")
    _ask(session, opening, ("Do you have the right to work in Spain?", True))
    question = opening.screening_questions[0]
    session.commit()

    response = _apply(client, opening.slug, answers=json.dumps({str(question.id): False}))

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == ApplicationState.EXTRACTED
    application = session.get(Application, body["application_id"])
    assert application is not None
    # Queued like everyone else: skipping the call is the pre-filter the plan rules out.
    queued = session.query(JobQueue).filter_by(application_id=application.id).count()
    assert queued == 1
    assert application.decision is None


def test_the_answer_is_recorded_against_the_question(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="scr-recorded")
    _ask(
        session,
        opening,
        ("Do you have the right to work in Spain?", True),
        ("Do you require visa sponsorship?", False),
    )
    first, second = opening.screening_questions
    session.commit()

    created = _apply(
        client,
        opening.slug,
        answers=json.dumps({str(first.id): True, str(second.id): True}),
    ).json()

    detail = client.get(f"/api/v1/applications/{created['application_id']}").json()
    answers = detail["screening_answers"]
    assert [a["text"] for a in answers] == [
        "Do you have the right to work in Spain?",
        "Do you require visa sponsorship?",
    ]
    assert [a["answer"] for a in answers] == [True, True]
    assert [a["matches"] for a in answers] == [True, False]


def test_the_reviewer_is_told_what_the_opening_was_asking_for(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """The one place `expected_answer` belongs: an answer alone cannot be read."""
    opening = make_opening(session, slug="scr-reviewer")
    _ask(session, opening, ("Do you require visa sponsorship?", False))
    question = opening.screening_questions[0]
    session.commit()

    created = _apply(client, opening.slug, answers=json.dumps({str(question.id): False})).json()
    detail = client.get(f"/api/v1/applications/{created['application_id']}").json()

    assert detail["screening_answers"][0]["expected_answer"] is False
    assert detail["screening_answers"][0]["matches"] is True


# --- What is refused, and why ---


def test_a_partial_set_of_answers_is_refused(client: TestClient, session: Session) -> None:
    """A gap reads on the panel exactly like a "no", which puts words in their mouth."""
    opening = make_opening(session, slug="scr-partial")
    _ask(session, opening, ("First?", True), ("Second?", True))
    first = opening.screening_questions[0]
    session.commit()

    response = _apply(client, opening.slug, answers=json.dumps({str(first.id): True}))
    assert response.status_code == 422
    assert "every question" in response.json()["detail"].lower()


def test_an_answer_to_another_opening_s_question_is_refused(
    client: TestClient, session: Session
) -> None:
    opening = make_opening(session, slug="scr-mine")
    elsewhere = make_opening(session, slug="scr-theirs")
    _ask(session, opening, ("Mine?", True))
    _ask(session, elsewhere, ("Theirs?", True))
    session.commit()

    response = _apply(
        client, opening.slug, answers=json.dumps({str(elsewhere.screening_questions[0].id): True})
    )
    assert response.status_code == 422


def test_a_non_boolean_answer_is_refused(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="scr-nonbool")
    _ask(session, opening, ("Do you?", True))
    question = opening.screening_questions[0]
    session.commit()

    response = _apply(client, opening.slug, answers=json.dumps({str(question.id): "yes"}))
    assert response.status_code == 422


def test_malformed_answers_do_not_reach_the_database(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="scr-garbage")
    _ask(session, opening, ("Do you?", True))
    session.commit()

    assert _apply(client, opening.slug, answers="not json at all").status_code == 422
    assert _apply(client, opening.slug, answers=json.dumps(["a", "list"])).status_code == 422
    assert session.query(Application).filter_by(job_opening_id=opening.id).count() == 0


def test_an_opening_that_asks_nothing_ignores_stray_answers(
    client: TestClient, session: Session
) -> None:
    """No questions, nothing to record. The applicant is not punished for noise."""
    opening = make_opening(session, slug="scr-ignores")
    session.commit()

    assert _apply(client, opening.slug, answers=json.dumps({})).status_code == 201


# --- The rubric contract ---


def test_an_opening_takes_at_most_five_questions(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    company = client.post("/api/v1/companies", json={"name": "Acme"}).json()
    payload = {
        "title": "Backend Engineer",
        "criteria": [
            {"name": "Python", "weight": 60, "mandatory": True},
            {"name": "Postgres", "weight": 40},
        ],
        "screening_questions": [{"text": f"Question {n}?"} for n in range(6)],
    }
    response = client.post(f"/api/v1/companies/{company['id']}/openings", json=payload)
    assert response.status_code == 422

    payload["screening_questions"] = [{"text": f"Question {n}?"} for n in range(5)]
    assert (
        client.post(f"/api/v1/companies/{company['id']}/openings", json=payload).status_code == 201
    )


def test_repeated_questions_are_refused(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    company = client.post("/api/v1/companies", json={"name": "Acme"}).json()
    response = client.post(
        f"/api/v1/companies/{company['id']}/openings",
        json={
            "title": "Backend Engineer",
            "criteria": [
                {"name": "Python", "weight": 60, "mandatory": True},
                {"name": "Postgres", "weight": 40},
            ],
            "screening_questions": [
                {"text": "Right to work?"},
                {"text": "  RIGHT TO WORK?  "},
            ],
        },
    )
    assert response.status_code == 422
