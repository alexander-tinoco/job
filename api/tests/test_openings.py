from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_opening

VALID_RUBRIC = [
    {"name": "Python", "weight": 60, "mandatory": True},
    {"name": "Postgres", "weight": 40},
]


def _create_company(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post("/api/v1/companies", json={"name": "Acme"}, headers=auth)
    assert response.status_code == 201
    return str(response.json()["id"])


def test_create_company_and_opening(client: TestClient, auth: dict[str, str]) -> None:
    company_id = _create_company(client, auth)

    response = client.post(
        f"/api/v1/companies/{company_id}/openings",
        json={
            "title": "Backend Engineer",
            "description": "Own our API.",
            "company_context": "Python shop, ships weekly.",
            "criteria": VALID_RUBRIC,
        },
        headers=auth,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["opening"]["slug"] == "backend-engineer"
    assert body["warnings"] == []
    assert [c["position"] for c in body["opening"]["criteria"]] == [1, 2]


def test_weights_that_miss_100_are_rejected_with_the_drift(
    client: TestClient, auth: dict[str, str]
) -> None:
    company_id = _create_company(client, auth)

    response = client.post(
        f"/api/v1/companies/{company_id}/openings",
        json={
            "title": "Backend Engineer",
            "criteria": [
                {"name": "Python", "weight": 60, "mandatory": True},
                {"name": "Postgres", "weight": 30},
            ],
        },
        headers=auth,
    )

    assert response.status_code == 422
    assert "they sum to 90 (10 under)" in response.text


def test_slug_collisions_resolve_automatically(client: TestClient, auth: dict[str, str]) -> None:
    company_id = _create_company(client, auth)
    payload = {"title": "Backend Engineer", "criteria": VALID_RUBRIC}

    first = client.post(f"/api/v1/companies/{company_id}/openings", json=payload, headers=auth)
    second = client.post(f"/api/v1/companies/{company_id}/openings", json=payload, headers=auth)

    assert first.json()["opening"]["slug"] == "backend-engineer"
    assert second.json()["opening"]["slug"] == "backend-engineer-2"


def test_accented_titles_produce_readable_slugs(client: TestClient, auth: dict[str, str]) -> None:
    company_id = _create_company(client, auth)

    response = client.post(
        f"/api/v1/companies/{company_id}/openings",
        json={"title": "Diseñador Gráfico", "criteria": VALID_RUBRIC},
        headers=auth,
    )

    assert response.json()["opening"]["slug"] == "disenador-grafico"


def test_dominant_criterion_is_returned_as_a_warning_not_an_error(
    client: TestClient, auth: dict[str, str]
) -> None:
    company_id = _create_company(client, auth)

    response = client.post(
        f"/api/v1/companies/{company_id}/openings",
        json={
            "title": "Backend Engineer",
            "criteria": [
                {"name": "Python", "weight": 70, "mandatory": True},
                {"name": "Postgres", "weight": 30},
            ],
        },
        headers=auth,
    )

    assert response.status_code == 201
    assert "70%" in response.json()["warnings"][0]


def test_public_page_hides_internal_fields(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    """Publishing the rubric would tell candidates exactly what to write."""
    opening = make_opening(session, slug="public-role")
    session.commit()

    response = client.get(f"/openings/{opening.slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Backend Engineer"
    assert body["company_name"] == "Acme"
    assert "company_context" not in body
    assert "criteria" not in body


def test_unknown_slug_is_a_404(client: TestClient) -> None:
    assert client.get("/openings/does-not-exist").status_code == 404


def test_rubric_templates_are_available_to_hr(client: TestClient, auth: dict[str, str]) -> None:
    response = client.get("/api/v1/rubric-templates", headers=auth)

    assert response.status_code == 200
    keys = {t["key"] for t in response.json()}
    assert "software_engineer" in keys


def test_private_endpoints_reject_an_anonymous_caller(client: TestClient) -> None:
    assert client.get("/api/v1/openings").status_code == 401


def test_closing_an_opening_flips_its_status(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    opening = make_opening(session, slug="to-close")
    session.commit()

    response = client.post(f"/api/v1/openings/{opening.id}/close", headers=auth)

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_private_endpoints_refuse_an_unknown_session(client: TestClient) -> None:
    """A forged or stale cookie is not a session."""
    client.cookies.set("screening_session", "not-a-real-token")

    response = client.get("/api/v1/openings")

    assert response.status_code == 401
    assert "session has expired" in response.text
