from datetime import datetime
from pydantic import BaseModel


class SessionBase(BaseModel):
    user_id: str
    token: str
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    expires_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class SessionResponse(SessionBase):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

