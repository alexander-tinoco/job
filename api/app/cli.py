"""Operational commands that ship inside the image.

    python -m app.cli create-user you@company.com "Your Name"
    python -m app.cli backfill-fingerprints

Distinct from `scripts/`, which is development tooling and deliberately excluded
from the container. Creating the first user is something a deployment has to do,
so it travels with the application.
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import select

from app.core.security import WeakPasswordError
from app.db.models import User
from app.db.session import SessionLocal
from app.services.auth import create_user, normalise_email
from app.services.duplicates import backfill


def _create_user(argv: list[str]) -> int:
    if len(argv) < 2:
        print('usage: python -m app.cli create-user <email> "<full name>"')
        return 2
    email, full_name = normalise_email(argv[0]), argv[1]

    with SessionLocal() as session:
        if session.scalar(select(User).where(User.email == email)) is not None:
            print(f"{email} already exists.")
            return 1

        # Prompted, never an argument: a command line ends up in shell history
        # and in the process list.
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat: "):
            print("Passwords do not match.")
            return 1

        try:
            create_user(session, email, full_name, password)
        except WeakPasswordError as exc:
            print(exc)
            return 1
        session.commit()

    print(f"Created {email}.")
    return 0


def _backfill_fingerprints(argv: list[str]) -> int:
    """Fingerprint résumés ingested before duplicate detection existed."""
    with SessionLocal() as session:
        count = backfill(session)
        session.commit()

    print(f"Fingerprinted {count} résumé(s).")
    return 0


COMMANDS = {
    "create-user": _create_user,
    "backfill-fingerprints": _backfill_fingerprints,
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in COMMANDS:
        print(f"usage: python -m app.cli [{' | '.join(COMMANDS)}] ...")
        return 2
    return COMMANDS[args[0]](args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
