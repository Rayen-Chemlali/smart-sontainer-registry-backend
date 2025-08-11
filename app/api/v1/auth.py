from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from app.api.schemas.auth import UserCreate, UserLogin, UserResponse, Token
from app.services.auth_service import AuthService
from app.api.auth import get_auth_service, get_current_active_user, security
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
        user_data: UserCreate,
        auth_service: AuthService = Depends(get_auth_service)
):
    """Enregistrer un nouvel utilisateur"""
    user = auth_service.register_user(user_data)
    return UserResponse.from_orm(user)


@router.post("/login", response_model=Token)
async def login(
        user_credentials: UserLogin,
        auth_service: AuthService = Depends(get_auth_service)
):
    """Connexion d'un utilisateur"""
    user = auth_service.authenticate_user(
        user_credentials.username,
        user_credentials.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth_service.access_token_expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="bearer")


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
        credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Déconnexion d'un utilisateur (côté client principalement)"""

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def read_users_me(
        current_user: User = Depends(get_current_active_user)
):
    """Récupérer les informations de l'utilisateur courant"""
    return UserResponse.from_orm(current_user)