from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.base_repository import BaseRepository
from app.models.chat_session import ChatSession


class ChatRepository(BaseRepository[ChatSession]):
    def __init__(self, db: Session):
        super().__init__(ChatSession, db)

    def get_by_session_id(self, session_id: str) -> Optional[ChatSession]:
        """Récupère une session de chat par son ID"""
        return self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()

    def get_user_sessions(self, user_id: str, limit: int = 10) -> List[ChatSession]:
        """Récupère les sessions d'un utilisateur"""
        return (self.db.query(ChatSession)
                .filter(ChatSession.user_id == user_id)
                .order_by(ChatSession.created_at.desc())
                .limit(limit)
                .all())