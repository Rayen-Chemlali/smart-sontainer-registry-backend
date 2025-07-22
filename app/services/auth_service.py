from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.repositories.user_repository import UserRepository
from app.models.user import User, UserRole
from app.api.schemas.auth import UserCreate, TokenData


class AuthService:
    """Service d'authentification"""

    def __init__(self, user_repository: UserRepository, secret_key: str, algorithm: str = "HS256"):
        self.user_repository = user_repository
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = 30

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash un mot de passe"""
        return self.pwd_context.hash(password)

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authentifie un utilisateur"""
        user = self.user_repository.get_by_username(username)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Crée un token d'accès JWT"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> TokenData:
        """Vérifie et décode un token JWT"""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")
            role: str = payload.get("role")

            if username is None:
                raise credentials_exception

            token_data = TokenData(username=username, role=UserRole(role) if role else None)
        except JWTError:
            raise credentials_exception

        return token_data

    def register_user(self, user_data: UserCreate) -> User:
        """Enregistre un nouvel utilisateur"""
        # Vérifier si l'utilisateur existe déjà
        if self.user_repository.username_exists(user_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )

        if self.user_repository.email_exists(user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hasher le mot de passe
        hashed_password = self.get_password_hash(user_data.password)

        # Créer l'utilisateur
        user_dict = {
            "username": user_data.username,
            "email": user_data.email,
            "hashed_password": hashed_password,
            "role": user_data.role,
            "is_active": True
        }

        return self.user_repository.create(user_dict)

    def get_current_user(self, token: str) -> User:
        """Récupère l'utilisateur courant à partir du token"""
        token_data = self.verify_token(token)
        user = self.user_repository.get_by_username(token_data.username)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user"
            )

        return user