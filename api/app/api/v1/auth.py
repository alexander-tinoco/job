from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.api.deps import SESSION_COOKIE, ClientIp, CurrentUser, SessionDep
from app.core.config import get_settings
from app.schemas.auth import LoginIn, UserOut
from app.services import auth

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

MAX_COOKIE_AGE = int(auth.ABSOLUTE_LIFETIME.total_seconds())


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=MAX_COOKIE_AGE,
        # No script can read it, so an XSS cannot exfiltrate the session.
        httponly=True,
        # Not sent over plain http. Off only for local development.
        secure=get_settings().cookie_secure,
        # Not attached to cross-site requests, which is what removes the CSRF
        # class here: another origin cannot make the browser act as this user.
        samesite="strict",
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginIn, response: Response, session: SessionDep, source_ip: ClientIp
) -> UserOut:
    """Sign in. Every failure answers the same way, on purpose."""
    try:
        issued = auth.authenticate(session, payload.email, payload.password, source_ip)
    except auth.RateLimitedError as exc:
        session.commit()  # The failure record must survive the rejection.
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except auth.AuthError as exc:
        session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = issued.session.user
    session.commit()
    _set_cookie(response, issued.token)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: SessionDep,
    screening_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """End the session on the server, not just in the browser.

    Clearing the cookie alone would leave a working session behind for anyone
    who copied the value.
    """
    if screening_session:
        auth.revoke(session, screening_session)
        session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
