"""Password hashing and session tokens.

The choices here are the ones an attacker actually meets, so each is stated with
its reason rather than left to a library default.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Argon2id: memory-hard, so a leaked hash costs an attacker RAM per guess rather
# than only cycles, which is what blunts GPU cracking. Parameters are explicit so
# a library default change cannot silently weaken every stored password.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB per verification
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# NIST SP 800-63B: length is what matters. No forced composition rules, because
# they push people towards "Password1!" and nothing else.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256

SESSION_TOKEN_BYTES = 32


class WeakPasswordError(ValueError):
    """The password does not meet the minimum requirements."""


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Passwords must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        # Bounded so a very long input cannot turn hashing into a denial of service.
        raise WeakPasswordError(f"Passwords must be at most {MAX_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError, InvalidHashError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than we use now."""
    try:
        return bool(_hasher.check_needs_rehash(password_hash))
    except InvalidHashError:
        return True


def waste_time_like_a_verification() -> None:
    """Hash a throwaway value when no user was found.

    Without this, a request for a non-existent email returns noticeably faster
    than one for a real email with the wrong password, which turns the login form
    into a way to enumerate accounts.
    """
    _hasher.hash("timing-equalisation")


def new_session_token() -> str:
    """The value that goes in the cookie. Never stored."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """What is stored instead.

    A plain SHA-256, not Argon2: the token is 256 bits of randomness, so there is
    nothing to brute-force and the per-request cost of a slow hash would buy
    nothing. The point is only that a database dump yields no usable sessions.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
