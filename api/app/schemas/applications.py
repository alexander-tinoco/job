import re
import uuid

from pydantic import BaseModel, field_validator

from app.db.types import ApplicationState

# Deliberately permissive. Real deliverability is proven when Resend accepts or
# bounces the address in Phase 9; this only rejects obvious garbage and gives us
# a usable deduplication key.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class ApplicantDetails(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    linkedin_url: str | None = None

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        """Lowercase before it becomes a key.

        The unique constraint is case-sensitive, so without this Ada@example.com
        and ada@example.com would become two different candidates.
        """
        cleaned = value.strip().lower()
        if not EMAIL_PATTERN.match(cleaned):
            raise ValueError("Not a valid email address.")
        return cleaned

    @field_validator("full_name")
    @classmethod
    def require_a_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name is required.")
        return cleaned


class ApplicationReceipt(BaseModel):
    application_id: uuid.UUID
    state: ApplicationState
    opening_title: str
    message: str
