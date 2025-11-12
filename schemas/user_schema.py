from pydantic import BaseModel


class UserBase(BaseModel):
    email: str
    name: str | None = None
    image: str | None = None


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: str | None = None
    image: str | None = None


class UserResponse(UserBase):
    id: str
    email_verified: bool

    model_config = {
        "from_attributes": True,
    }
