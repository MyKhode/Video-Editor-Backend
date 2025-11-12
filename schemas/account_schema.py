from datetime import datetime
from pydantic import BaseModel


class AccountBase(BaseModel):
    user_id: str
    account_id: str | None = None
    provider_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    scope: str | None = None
    password: str | None = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    pass


class AccountResponse(AccountBase):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

