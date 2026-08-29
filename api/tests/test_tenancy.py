"""One company per deployment, enforced rather than assumed.

The MVP has no tenant on `User` (plan §7, "Out"): the panel shows every opening
in the database to everyone who can sign in. That is correct for one company and
a silent leak for two — one client's HR reading another's candidates.

The assumption was written in the plan and the code allowed the opposite, which
is the shape most tenancy leaks have. These tests hold the line.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Company
from tests.factories import make_opening


def test_the_first_company_is_created(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post("/api/v1/companies", json={"name": "Mercadis"})

    assert response.status_code == 201
    assert response.json()["name"] == "Mercadis"


def test_a_second_company_is_refused(client: TestClient, auth: dict[str, str]) -> None:
    client.post("/api/v1/companies", json={"name": "Mercadis"})

    response = client.post("/api/v1/companies", json={"name": "Nurex"})

    assert response.status_code == 409
    detail = response.json()["detail"]
    # The refusal has to say why, or the next person works around it.
    assert "Mercadis" in detail
    assert "second deployment" in detail.lower()


def test_the_refusal_leaves_the_first_company_alone(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    client.post("/api/v1/companies", json={"name": "Mercadis"})
    client.post("/api/v1/companies", json={"name": "Nurex"})

    companies = session.query(Company).all()
    assert [c.name for c in companies] == ["Mercadis"]


def test_the_panel_still_shows_every_opening_of_that_one_company(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """The guard exists precisely because this listing has no tenant filter."""
    first = make_opening(session, slug="tenancy-one")
    second = make_opening(session, slug="tenancy-two")
    second.company = first.company
    session.commit()

    slugs = {o["slug"] for o in client.get("/api/v1/openings").json()}

    assert {"tenancy-one", "tenancy-two"} <= slugs


def test_creating_a_company_needs_a_session(client: TestClient) -> None:
    assert client.post("/api/v1/companies", json={"name": "Mercadis"}).status_code == 401
