from functools import lru_cache
from typing import Generator
from sqlalchemy.orm import Session
from fastapi import Depends

from app.external.s3_client import S3Client
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
from app.external.groq_client import GroqClient
from app.services.registry_service import RegistryService
from app.services.k8s_service import K8sService
from app.services.overview_service import OverviewService
from app.services.chatbot_service import ChatbotService
from app.config import settings
from app.repositories.rule_repository import RuleRepository
from app.services.rule_engine import RuleEngine

from app.core.database import get_db
from app.repositories.base_repository import BaseRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.sync_repository import SyncRepository
from app.repositories.chat_repository import ChatRepository

# === CLIENTS EXTERNES ===
@lru_cache()
def get_s3_client() -> S3Client:
    return S3Client(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )

@lru_cache()
def get_registry_client() -> RegistryClient:
    return RegistryClient(
        base_url=settings.REGISTRY_URL,
        minio_endpoint=settings.MINIO_ENDPOINT,
        minio_access_key=settings.MINIO_ACCESS_KEY,
        minio_secret_key=settings.MINIO_SECRET_KEY,
        minio_secure=settings.MINIO_SECURE
    )

@lru_cache()
def get_k8s_client() -> K8sClient:
    return K8sClient()

@lru_cache()
def get_groq_client() -> GroqClient:
    return GroqClient(settings.GROQ_API_KEY)

# === REPOSITORIES ===
def get_image_repository(db: Session = Depends(get_db)) -> ImageRepository:
    """Factory pour le repository des images"""
    return ImageRepository(db)

def get_deployment_repository(db: Session = Depends(get_db)) -> DeploymentRepository:
    """Factory pour le repository des déploiements"""
    return DeploymentRepository(db)

def get_sync_repository(db: Session = Depends(get_db)) -> SyncRepository:
    """Factory pour le repository des logs de synchronisation"""
    return SyncRepository(db)

def get_chat_repository(db: Session = Depends(get_db)) -> ChatRepository:
    """Factory pour le repository des sessions de chat"""
    return ChatRepository(db)
def get_rule_repository(db: Session = Depends(get_db)) -> RuleRepository:
    """Factory pour le repository des règles"""
    return RuleRepository(db)

# === SERVICES ===
def get_rule_engine(
    db: Session = Depends(get_db)
) -> RuleEngine:
    """Factory pour le moteur de règles"""
    return RuleEngine(db)

def get_registry_service() -> RegistryService:
    return RegistryService(get_registry_client(), get_k8s_client())

def get_k8s_service() -> K8sService:
    return K8sService(get_k8s_client())

def get_overview_service() -> OverviewService:
    return OverviewService(get_s3_client(), get_registry_service(), get_k8s_service())

def get_chatbot_service(
    chat_repo: ChatRepository = Depends(get_chat_repository)
) -> ChatbotService:
    """Factory pour le service chatbot avec repository"""
    return ChatbotService(
        groq_client=get_groq_client(),
        registry_service=get_registry_service(),
        k8s_service=get_k8s_service(),
        overview_service=get_overview_service(),
        s3_client=get_s3_client(),
        chat_repository=get_chat_repository()
    )