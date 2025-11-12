from pydantic import BaseModel
from schemas.user_schema import UserResponse


class GoogleLoginRequest(BaseModel):
    token: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LoginUrlResponse(BaseModel):
    url: str
