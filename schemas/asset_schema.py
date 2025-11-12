from datetime import datetime
from pydantic import BaseModel


class AssetBase(BaseModel):
    user_id: str
    original_name: str
    storage_key: str
    mime_type: str
    size_bytes: int
    project_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    project_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


class AssetResponse(AssetBase):
    id: str
    created_at: datetime | None = None
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}

