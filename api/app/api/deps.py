import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    """Placeholder guard for the private endpoints until Phase 8 brings real auth.

    Fails closed: an unset ADMIN_TOKEN denies every request rather than opening
    the CRUD to the internet. compare_digest keeps the check constant-time.
    """
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN is not configured; private endpoints are disabled.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")


SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[None, Depends(require_admin)]
