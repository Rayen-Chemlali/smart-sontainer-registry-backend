from pydantic import BaseModel, EmailStr
from typing import Optional
from app.models.user import UserRole


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[UserRole] = UserRole.USER


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    role: UserRole

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None