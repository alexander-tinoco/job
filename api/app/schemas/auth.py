import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    # Not bounded low here: the real requirement lives in core.security, and a
    # length hint on the login form would leak the policy to anyone guessing.
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    last_login_at: datetime | None
