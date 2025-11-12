from datetime import datetime
from pydantic import BaseModel


class VerificationBase(BaseModel):
    identifier: str
    value: str
    expires_at: datetime


class VerificationCreate(VerificationBase):
    pass


class VerificationUpdate(BaseModel):
    value: str | None = None
    expires_at: datetime | None = None


class VerificationResponse(VerificationBase):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

