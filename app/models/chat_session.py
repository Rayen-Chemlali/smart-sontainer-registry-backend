from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class ChatSession(BaseModel):
    __tablename__ = "chat_sessions"

    session_id = Column(String(255), unique=True, nullable=False)
    user_id = Column(String(255), nullable=False)

    # Statut
    is_active = Column(Boolean, default=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relations
    messages = relationship("ChatMessage", back_populates="session")


class ChatMessage(BaseModel):
    __tablename__ = "chat_messages"

    session_id = Column(Integer, ForeignKey("chat_sessions.id"))

    # Contenu
    message_type = Column(String(50))  # user, bot, system
    content = Column(Text, nullable=False)

    # IA
    detected_intent = Column(String(100))
    confidence = Column(Integer)  # 0-100

    # Timing
    timestamp = Column(DateTime)

    # Relations
    session = relationship("ChatSession", back_populates="messages")