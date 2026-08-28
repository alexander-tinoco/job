import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import OutreachKind, OutreachState


class OutreachOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    candidate_name: str
    candidate_email: str
    kind: OutreachKind
    state: OutreachState
    subject: str
    body: str
    template_version: str
    approved_by: str | None
    sent_at: datetime | None
    last_error: str | None


class OutreachEdit(BaseModel):
    """HR may rewrite a draft before it goes out. That is the point of a draft."""

    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class SendRequest(BaseModel):
    # Sending is an act by a person, and the record says who. There is no
    # endpoint that sends without one.
    approved_by: str = Field(min_length=1, max_length=200)
