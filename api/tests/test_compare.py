"""Two candidates beside each other.

The point of these tests is the arithmetic that answers "why is one ahead":
the gap between two overall scores must decompose exactly into the criteria.
"""

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.schema import EvaluationOutput
from app.db.models import Application, IntegrityReport, ResumeDocument
from app.db.types import IntegrityVerdict
from app.services.evaluation import persist_evaluation
from tests.factories import make_application, make_opening

FIXTURES = Path(__file__).parent / "fixtures"
# Every fixture below was produced from this one résumé, so their quotes all
# verify against it and the comparison rows differ only in the scores.
RESUME_TEXT: str = json.loads((FIXTURES / "strong_candidate.json").read_text(encoding="utf-8"))[
    "resume_text"
]


def _evaluated(
    session: Session,
    opening: object,
    email: str,
    fixture: str,
    scores: dict[str, int] | None = None,
) -> Application:
    output = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["output"]
    for criterion in output["criteria"]:
        if scores and criterion["criterion_name"] in scores:
            criterion["score"] = scores[criterion["criterion_name"]]
    application = make_application(session, opening, email)  # type: ignore[arg-type]
    application.resume = ResumeDocument(
        storage_path=f"{application.id}/cv.pdf",
        visible_text=RESUME_TEXT,
        total_text=RESUME_TEXT,
    )
    session.flush()
    persist_evaluation(session, application, EvaluationOutput.model_validate(output))
    session.flush()
    return application


def _compare(client: TestClient, opening_id: object, *ids: object) -> dict[str, object]:
    query = "&".join(f"ids={i}" for i in ids)
    response = client.get(f"/api/v1/openings/{opening_id}/compare?{query}")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_gap_decomposes_exactly_into_the_criteria(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Sum the per-criterion differences and you get the difference in the totals.

    This is the whole promise of the screen: not "84 against 72" but "the twelve
    points are Python".
    """
    opening = make_opening(session, slug="cmp-gap")
    strong = _evaluated(session, opening, "a@x.com", "mini_medium.json")
    weaker = _evaluated(session, opening, "b@x.com", "strong_candidate.json")
    session.commit()

    body = _compare(client, opening.id, strong.id, weaker.id)

    totals = {c["id"]: Decimal(c["overall_score"]) for c in body["candidates"]}
    overall_gap = totals[str(strong.id)] - totals[str(weaker.id)]

    summed = Decimal("0")
    for row in body["criteria"]:
        by_id = {s["application_id"]: Decimal(s["contribution"]) for s in row["sides"]}
        summed += by_id[str(strong.id)] - by_id[str(weaker.id)]

    assert summed == overall_gap
    assert overall_gap == Decimal("12.00")


def test_the_decisive_criterion_is_named(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Both scored the same on Postgres, so only Python separates them."""
    opening = make_opening(session, slug="cmp-decisive")
    strong = _evaluated(session, opening, "a@y.com", "mini_medium.json")
    weaker = _evaluated(session, opening, "b@y.com", "strong_candidate.json")
    session.commit()

    body = _compare(client, opening.id, strong.id, weaker.id)

    assert body["decisive"] == ["Python"]
    rows = {r["criterion_name"]: r for r in body["criteria"]}
    assert rows["Python"]["leaders"] == [str(strong.id)]
    assert rows["Postgres"]["leaders"] == []
    assert Decimal(rows["Postgres"]["spread"]) == Decimal("0.00")


def test_a_tie_crowns_nobody(client: TestClient, session: Session, auth: dict[str, str]) -> None:
    """Two identical evaluations must not manufacture a winner."""
    opening = make_opening(session, slug="cmp-tie")
    one = _evaluated(session, opening, "a@z.com", "strong_candidate.json")
    two = _evaluated(session, opening, "b@z.com", "strong_candidate.json")
    session.commit()

    body = _compare(client, opening.id, one.id, two.id)

    assert body["decisive"] == []
    assert all(row["leaders"] == [] for row in body["criteria"])


def test_the_columns_keep_the_order_they_were_asked_for(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Whoever compares chose which one sits on the left."""
    opening = make_opening(session, slug="cmp-order")
    first = _evaluated(session, opening, "a@o.com", "strong_candidate.json")
    second = _evaluated(session, opening, "b@o.com", "mini_medium.json")
    session.commit()

    body = _compare(client, opening.id, second.id, first.id)
    assert [c["id"] for c in body["candidates"]] == [str(second.id), str(first.id)]


def test_the_evidence_shown_is_only_the_verified_quotes(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """A quote that was not found in the résumé never reaches a comparison."""
    opening = make_opening(session, slug="cmp-quotes")
    one = _evaluated(session, opening, "a@q.com", "strong_candidate.json")
    two = _evaluated(session, opening, "b@q.com", "mini_medium.json")
    # Break one quote exactly as the verifier would have marked it.
    score = one.evaluation.scores[0]  # type: ignore[union-attr]
    score.evidence = [{"quote": "Never written anywhere.", "found": False, "start": None}]
    session.commit()

    body = _compare(client, opening.id, one.id, two.id)

    side = next(
        s
        for row in body["criteria"]
        for s in row["sides"]
        if s["application_id"] == str(one.id) and row["criterion_name"] == "Python"
    )
    assert side["quotes"] == []


def test_a_tampered_resume_is_flagged_in_the_column(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """The warning must survive the trip into a side-by-side view."""
    opening = make_opening(session, slug="cmp-tampered")
    one = _evaluated(session, opening, "a@t.com", "strong_candidate.json")
    two = _evaluated(session, opening, "b@t.com", "mini_medium.json")
    one.integrity = IntegrityReport(verdict=IntegrityVerdict.TAMPERED, hidden_spans=[])
    session.commit()

    body = _compare(client, opening.id, one.id, two.id)
    flags = {c["id"]: c["tampered"] for c in body["candidates"]}
    assert flags[str(one.id)] is True
    assert flags[str(two.id)] is False


def test_an_unexamined_candidate_cannot_be_compared(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """There is nothing to line up, and inventing zeros would be a lie."""
    opening = make_opening(session, slug="cmp-unexamined")
    evaluated = _evaluated(session, opening, "a@u.com", "strong_candidate.json")
    pending = make_application(session, opening, "b@u.com")
    session.commit()

    response = client.get(
        f"/api/v1/openings/{opening.id}/compare?ids={evaluated.id}&ids={pending.id}"
    )
    assert response.status_code == 409


def test_a_candidate_from_another_opening_is_not_comparable(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Different rubrics, different weights: the rows would not mean the same thing."""
    here = make_opening(session, slug="cmp-here")
    elsewhere = make_opening(session, slug="cmp-elsewhere")
    mine = _evaluated(session, here, "a@e.com", "strong_candidate.json")
    theirs = _evaluated(session, elsewhere, "b@e.com", "mini_medium.json")
    session.commit()

    response = client.get(f"/api/v1/openings/{here.id}/compare?ids={mine.id}&ids={theirs.id}")
    assert response.status_code == 409


def test_comparing_more_than_three_is_refused(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="cmp-many")
    ids = [_evaluated(session, opening, f"{n}@m.com", "strong_candidate.json").id for n in range(4)]
    session.commit()

    query = "&".join(f"ids={i}" for i in ids)
    response = client.get(f"/api/v1/openings/{opening.id}/compare?{query}")
    assert response.status_code == 400


def test_comparing_needs_a_session(client: TestClient, session: Session) -> None:
    opening = make_opening(session, slug="cmp-auth")
    one = _evaluated(session, opening, "a@n.com", "strong_candidate.json")
    two = _evaluated(session, opening, "b@n.com", "mini_medium.json")
    session.commit()

    response = client.get(f"/api/v1/openings/{opening.id}/compare?ids={one.id}&ids={two.id}")
    assert response.status_code == 401


def test_one_criterion_is_named_when_one_criterion_is_the_story(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Python alone carries the whole gap, so naming a second would be padding."""
    opening = make_opening(session, slug="cmp-single")
    strong = _evaluated(session, opening, "a@s.com", "mini_medium.json")
    weaker = _evaluated(session, opening, "b@s.com", "strong_candidate.json")
    session.commit()

    body = _compare(client, opening.id, strong.id, weaker.id)
    assert body["decisive"] == ["Python"]


def test_a_gap_split_evenly_names_both_criteria(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Neither row alone passes half the difference, so neither may be singled out.

    Python is weighted 60 and Postgres 40, so two points of Python and three of
    Postgres are worth exactly the same 24 points of the total.
    """
    opening = make_opening(session, slug="cmp-spread")
    strong = _evaluated(
        session, opening, "a@p.com", "mini_medium.json", {"Python": 5, "Postgres": 3}
    )
    weaker = _evaluated(
        session, opening, "b@p.com", "mini_medium.json", {"Python": 3, "Postgres": 0}
    )
    session.commit()

    body = _compare(client, opening.id, strong.id, weaker.id)

    rows = {r["criterion_name"]: Decimal(r["spread"]) for r in body["criteria"]}
    assert rows["Python"] == rows["Postgres"] == Decimal("24.00")
    assert body["decisive"] == ["Python", "Postgres"]
