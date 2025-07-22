from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.orm import relationship
import enum
from app.models.base import BaseModel


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(BaseModel):
    __tablename__ = "users"

    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)

    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}', role='{self.role}')>"