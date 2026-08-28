import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor: str
    action: str
    entity_type: str
    entity_id: uuid.UUID
    payload: dict[str, object]
    created_at: datetime


class ErasureRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ErasureResult(BaseModel):
    applications: int
    files_deleted: int


class SweepResult(BaseModel):
    applications: int
    files_deleted: int
    files_missing: int
