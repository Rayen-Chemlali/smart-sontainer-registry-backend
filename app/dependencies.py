from functools import lru_cache
from typing import Generator
from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.function_registry import FunctionRegistry
from app.workers.rule_evaluation_worker import RuleEvaluationWorker

from app.external.s3_client import S3Client
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
from app.external.groq_client import GroqClient
from app.services.registry_service import RegistryService
from app.services.k8s_service import K8sService
from app.services.overview_service import OverviewService
from app.services.chatbot_service import ChatbotService
from app.services.auth_service import AuthService
from app.config import settings
from app.repositories.rule_repository import RuleRepository
from app.services.rule_engine import RuleEngine

from app.core.database import get_db
from app.repositories.base_repository import BaseRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.sync_repository import SyncRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository


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


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """Factory pour le repository des utilisateurs"""
    return UserRepository(db)


# === SERVICES ===
def get_rule_engine(
        db: Session = Depends(get_db)
) -> RuleEngine:
    """Factory pour le moteur de règles"""
    return RuleEngine(db)


@lru_cache()
def get_registry_service() -> RegistryService:
    """FIXED: Create registry service and fix ImageFilterCriteria"""
    registry_service = RegistryService(get_registry_client(), get_k8s_client())

    # FIXED: Import and assign the enum class properly
    from enum import Enum

    class ImageFilterCriteria(Enum):
        """Critères de filtrage des images"""
        ALL = "all"
        DEPLOYED = "deployed"
        NOT_DEPLOYED = "not_deployed"
        OLDER_THAN = "older_than"
        MODIFIED_BEFORE = "modified_before"
        LARGER_THAN = "larger_than"
        UNUSED_TAGS = "unused_tags"

    # Assign the enum class to the service instance
    registry_service.ImageFilterCriteria = ImageFilterCriteria

    return registry_service


def get_k8s_service() -> K8sService:
    return K8sService(get_k8s_client())


def get_overview_service() -> OverviewService:
    return OverviewService(get_s3_client(), get_registry_service(), get_k8s_service())




def get_auth_service(
        user_repo: UserRepository = Depends(get_user_repository)
) -> AuthService:
    """Factory pour le service d'authentification"""
    return AuthService(
        user_repository=user_repo,
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )


# === WORKERS ===
_rule_worker_instance = None


def get_rule_evaluation_worker() -> RuleEvaluationWorker:
    """Factory pour le worker d'évaluation des règles (singleton)"""
    global _rule_worker_instance
    if _rule_worker_instance is None:
        registry_service = get_registry_service()
        _rule_worker_instance = RuleEvaluationWorker(registry_service)
    return _rule_worker_instance


function_registry = FunctionRegistry()
def get_chatbot_service() -> ChatbotService:
    """Factory pour créer le service chatbot avec dynamic function calling"""

    # Initialiser les clients externes
    groq_client = get_groq_client()


    # Initialiser les services
    k8s_service = get_k8s_service()
    registry_service =get_registry_service()


    # Initialiser et remplir le registre des fonctions


    function_registry.register_service(
        "docker_registry",
        registry_service,
        description="Gestion des registres de conteneurs Docker",
        domains=["docker", "registry", "containers", "images"]
    )

    function_registry.register_service(
        "kubernetes",
        k8s_service,
        description="Gestion des clusters et ressources Kubernetes",
        domains=["kubernetes", "k8s", "pods", "deployments", "services"]
    )
    # Créer le service chatbot
    chatbot_service = ChatbotService(groq_client=groq_client, function_registry=function_registry)

    return chatbot_service
