"""Throttling the endpoints a stranger can reach.

The public application form is the expensive one: no session, a 10 MB upload, an
inline PyMuPDF pass and a queue row that becomes a paid model call. Sign-in has
been limited since the beginning; this had nothing.

Two duties pull against each other here, and the tests are split accordingly:
refuse a flood, and never refuse a real candidate who simply shares an office.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, LoginAttempt, RateEvent
from app.services import limits
from tests.factories import make_opening
from tests.pdfs import make_resume

FORM = {"full_name": "Ada Lovelace", "email": "ada@example.com", "consent": "true"}


def _apply(client: TestClient, slug: str, **overrides: object) -> object:
    return client.post(
        f"/openings/{slug}/apply",
        data={**FORM, **overrides},
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
    )


# --- Refusing a flood ---


def test_one_applicant_cannot_send_without_end(client: TestClient, session: Session) -> None:
    openings = [make_opening(session, slug=f"lim-mine-{n}") for n in range(7)]
    session.commit()

    codes = [_apply(client, opening.slug).status_code for opening in openings]

    assert codes[: limits.MAX_APPLICATIONS_PER_EMAIL] == [201] * limits.MAX_APPLICATIONS_PER_EMAIL
    assert codes[limits.MAX_APPLICATIONS_PER_EMAIL] == 429
    assert set(codes[limits.MAX_APPLICATIONS_PER_EMAIL :]) == {429}


def test_the_refusal_happens_before_anything_is_stored(
    client: TestClient, session: Session
) -> None:
    """The point of the limit: no disk write, no extraction, no queue row."""
    openings = [make_opening(session, slug=f"lim-cost-{n}") for n in range(6)]
    session.commit()
    for opening in openings[:5]:
        _apply(client, opening.slug)

    before = session.query(Application).count()
    response = _apply(client, openings[5].slug)

    assert response.status_code == 429
    assert session.query(Application).count() == before


def test_one_address_cannot_flood_under_many_names(client: TestClient, session: Session) -> None:
    """The per-email limit alone is defeated by inventing an address each time."""
    openings = [make_opening(session, slug=f"lim-ip-{n}") for n in range(25)]
    session.commit()

    codes = []
    for index, opening in enumerate(openings):
        codes.append(_apply(client, opening.slug, email=f"person{index}@example.com").status_code)

    assert codes.count(201) == limits.MAX_APPLICATIONS_PER_IP
    assert codes[limits.MAX_APPLICATIONS_PER_IP] == 429


def test_a_refusal_does_not_extend_the_lockout(client: TestClient, session: Session) -> None:
    """Counting refusals would let a blocked caller keep their own ban alive."""
    openings = [make_opening(session, slug=f"lim-knock-{n}") for n in range(6)]
    session.commit()
    for opening in openings[:5]:
        _apply(client, opening.slug)

    recorded = session.query(RateEvent).filter_by(scope=limits.APPLY_EMAIL).count()
    for _ in range(4):
        assert _apply(client, openings[5].slug).status_code == 429

    assert session.query(RateEvent).filter_by(scope=limits.APPLY_EMAIL).count() == recorded


# --- Not refusing a real candidate ---


def test_the_window_moves(client: TestClient, session: Session) -> None:
    """Yesterday's applications must not count against today's."""
    openings = [make_opening(session, slug=f"lim-window-{n}") for n in range(6)]
    session.commit()
    for opening in openings[:5]:
        _apply(client, opening.slug)

    old = limits.now() - limits.WINDOW - timedelta(minutes=1)
    for event in session.scalars(select(RateEvent)):
        event.created_at = old
    session.commit()

    assert _apply(client, openings[5].slug).status_code == 201


def test_two_people_behind_one_address_are_counted_apart(
    client: TestClient, session: Session
) -> None:
    """A shared office is the case that must not be mistaken for a flood."""
    openings = [make_opening(session, slug=f"lim-shared-{n}") for n in range(6)]
    session.commit()
    for opening in openings[:5]:
        _apply(client, opening.slug, email="first@example.com")

    assert _apply(client, openings[5].slug, email="second@example.com").status_code == 201


def test_the_email_is_matched_however_it_is_written(session: Session) -> None:
    assert limits.fingerprint("Ada@Example.com ") == limits.fingerprint("ada@example.com")


# --- What is kept ---


def test_the_address_is_never_stored_in_the_clear(client: TestClient, session: Session) -> None:
    """A dump of the throttle table must not be a list of who applied."""
    opening = make_opening(session, slug="lim-privacy")
    session.commit()
    _apply(client, opening.slug, email="ada@example.com")

    keys = {event.key for event in session.scalars(select(RateEvent))}
    assert "ada@example.com" not in keys
    assert limits.fingerprint("ada@example.com") in keys


def test_the_sweep_drops_both_throttle_tables(session: Session) -> None:
    """`login_attempts` had no sweep of its own and grew without bound."""
    old = limits.now() - limits.RETENTION - timedelta(hours=1)
    session.add_all(
        [
            RateEvent(scope=limits.APPLY_IP, key="1.2.3.4", created_at=old),
            LoginAttempt(email="old@example.com", source_ip="1.2.3.4", created_at=old),
            RateEvent(scope=limits.APPLY_IP, key="5.6.7.8"),
            LoginAttempt(email="fresh@example.com", source_ip="5.6.7.8"),
        ]
    )
    session.flush()

    assert limits.sweep(session) == 2
    assert {e.key for e in session.scalars(select(RateEvent))} == {"5.6.7.8"}
    assert {a.email for a in session.scalars(select(LoginAttempt))} == {"fresh@example.com"}


def test_a_sweep_with_nothing_stale_changes_nothing(session: Session) -> None:
    session.add(RateEvent(scope=limits.APPLY_IP, key="1.2.3.4"))
    session.flush()

    assert limits.sweep(session) == 0
    assert session.query(RateEvent).count() == 1


@pytest.mark.parametrize("header", ["203.0.113.9", "203.0.113.9, 10.0.0.1"])
def test_the_forwarded_address_is_the_one_throttled(
    client: TestClient, session: Session, header: str
) -> None:
    """Behind a proxy the socket address is the proxy, so every caller looks alike."""
    opening = make_opening(session, slug=f"lim-fwd-{len(header)}")
    session.commit()

    client.post(
        f"/openings/{opening.slug}/apply",
        data=FORM,
        files={"resume": ("cv.pdf", make_resume(), "application/pdf")},
        headers={"X-Forwarded-For": header},
    )

    keys = {
        e.key for e in session.scalars(select(RateEvent).where(RateEvent.scope == limits.APPLY_IP))
    }
    assert keys == {"203.0.113.9"}
