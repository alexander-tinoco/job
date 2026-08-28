from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import SessionLocal
from app.services import auth

# HttpOnly, so no script on the page can read it. This is the whole reason the
# session does not live in localStorage: an XSS can act as the user while the
# page is open, but it cannot steal a credential and use it later from
# somewhere else.
SESSION_COOKIE = "screening_session"


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def current_user(
    session: SessionDep,
    screening_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    if not screening_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    user = auth.resolve_session(session, screening_session)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Your session has expired.")
    session.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def client_ip(request: Request) -> str:
    """The address to throttle on.

    Behind a proxy the socket address is the proxy, so the first hop of
    X-Forwarded-For is used when present. That header is client-controlled and
    therefore only ever used for rate limiting, never for authorisation.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


ClientIp = Annotated[str, Depends(client_ip)]
