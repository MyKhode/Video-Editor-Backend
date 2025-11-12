from datetime import datetime
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    name: str
    timeline: dict | None = None
    text_bin_items: list | None = Field(default=None, alias="textBinItems")


class ProjectCreate(ProjectBase):
    """Client payload for creating a project. User is inferred from auth."""
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    timeline: dict | None = None
    text_bin_items: list | None = Field(default=None, alias="textBinItems")


class ProjectResponse(ProjectBase):
    id: str
    user_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "alias_generator": None,
    }
