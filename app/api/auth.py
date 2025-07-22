from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.models.user import User, UserRole
from app.config import settings

# Sécurité Bearer Token
security = HTTPBearer()

def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """Factory pour le repository des utilisateurs"""
    return UserRepository(db)

def get_auth_service(user_repo: UserRepository = Depends(get_user_repository)) -> AuthService:
    """Factory pour le service d'authentification"""
    return AuthService(
        user_repository=user_repo,
        secret_key=getattr(settings, 'SECRET_KEY', 'your-secret-key-change-this-in-production'),
        algorithm="HS256"
    )

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """Récupère l'utilisateur courant à partir du token"""
    return auth_service.get_current_user(credentials.credentials)

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Récupère l'utilisateur courant actif"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Vérifie que l'utilisateur courant est admin"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user