import uuid

from pydantic import BaseModel


class DuplicateMatch(BaseModel):
    application_id: uuid.UUID
    candidate_name: str
    opening_title: str
    # Estimated overlap of the two documents, 0.0 to 1.0.
    similarity: float
    identical: bool
    # False is the finding: one document, two identities.
    same_person: bool


class DuplicatesOut(BaseModel):
    matches: list[DuplicateMatch]
