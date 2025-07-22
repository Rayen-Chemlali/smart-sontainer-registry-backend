from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.repositories.base_repository import BaseRepository
from app.models.user import User


class UserRepository(BaseRepository[User]):
    """Repository pour la gestion des utilisateurs"""

    def __init__(self, db: Session):
        super().__init__(User, db)

    def get_by_username(self, username: str) -> Optional[User]:
        """Récupère un utilisateur par son nom d'utilisateur"""
        try:
            return self.db.query(User).filter(User.username == username).first()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def get_by_email(self, email: str) -> Optional[User]:
        """Récupère un utilisateur par son email"""
        try:
            return self.db.query(User).filter(User.email == email).first()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def username_exists(self, username: str) -> bool:
        """Vérifie si un nom d'utilisateur existe déjà"""
        try:
            return self.db.query(User).filter(User.username == username).first() is not None
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def email_exists(self, email: str) -> bool:
        """Vérifie si un email existe déjà"""
        try:
            return self.db.query(User).filter(User.email == email).first() is not None
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e