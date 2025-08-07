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


def get_registry_service(
        image_repo: ImageRepository = Depends(get_image_repository)
) -> RegistryService:
    """Factory pour le service de registre avec ImageRepository"""
    registry_service = RegistryService(
        registry_client=get_registry_client(),
        k8s_client=get_k8s_client(),
        image_repository=image_repo
    )

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
_chatbot_service_instance = None


def get_rule_evaluation_worker() -> RuleEvaluationWorker:
    """Factory pour le worker d'évaluation des règles (singleton)"""
    global _rule_worker_instance
    if _rule_worker_instance is None:
        registry_service = get_registry_service()
        _rule_worker_instance = RuleEvaluationWorker(registry_service)
    return _rule_worker_instance


# Instance globale du registre des fonctions
function_registry = FunctionRegistry()


def get_chatbot_service() -> ChatbotService:
    """Factory pour créer le service chatbot avec dynamic function calling (singleton)"""
    global _chatbot_service_instance

    if _chatbot_service_instance is None:
        # Initialiser les clients externes
        groq_client = get_groq_client()

        # Initialiser les services
        k8s_service = get_k8s_service()

        # 🔥 SOLUTION 1: Créer une session DB en utilisant le générateur get_db()
        from app.core.database import get_db
        db_generator = get_db()
        db_session = next(db_generator)
        rule_engine = RuleEngine(db_session)

        # Note: Pour registry_service, on utilise une version sans dépendance DB
        registry_service = RegistryService(
            registry_client=get_registry_client(),
            k8s_client=get_k8s_client(),
            image_repository=None
        )

        # Ajouter l'enum au service
        from enum import Enum
        class ImageFilterCriteria(Enum):
            ALL = "all"
            DEPLOYED = "deployed"
            NOT_DEPLOYED = "not_deployed"
            OLDER_THAN = "older_than"
            MODIFIED_BEFORE = "modified_before"
            LARGER_THAN = "larger_than"
            UNUSED_TAGS = "unused_tags"

        registry_service.ImageFilterCriteria = ImageFilterCriteria

        # Initialiser et remplir le registre des fonctions
        function_registry.register_service(
            "registry_service",
            registry_service,
            description="Gestion des registres de conteneurs Docker",
            domains=["docker", "registry", "containers", "images"]
        )

        function_registry.register_service(
            "kubernetes_service",
            k8s_service,
            description="Gestion des clusters et ressources Kubernetes",
            domains=["kubernetes", "k8s", "pods", "deployments", "services"]
        )

        # Enregistrer le service rules_engine
        function_registry.register_service(
            "rules_engine",
            rule_engine,
            description="Moteur de règles pour la gestion automatique des images et conteneurs",
            domains=["rules", "automation", "cleanup", "policies", "règles", "automatisation"]
        )

        # Créer l'instance unique du service chatbot
        _chatbot_service_instance = ChatbotService(
            groq_client=groq_client,
            function_registry=function_registry
        )

    return _chatbot_service_instance


# === ALTERNATIVE: Factory avec repository injection si nécessaire ===
def get_chatbot_service_with_db(
        image_repo: ImageRepository = Depends(get_image_repository)
) -> ChatbotService:
    """
    Alternative factory si vous avez besoin d'injecter des repositories
    dans le service chatbot. Cette version n'est PAS un singleton.
    Utilisez get_chatbot_service() pour la version singleton.
    """
    # Initialiser les clients externes
    groq_client = get_groq_client()

    # Initialiser les services avec repository
    k8s_service = get_k8s_service()
    registry_service = RegistryService(
        registry_client=get_registry_client(),
        k8s_client=get_k8s_client(),
        image_repository=image_repo
    )

    # Ajouter l'enum au service
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

    registry_service.ImageFilterCriteria = ImageFilterCriteria

    # Créer un nouveau registre des fonctions
    local_function_registry = FunctionRegistry()

    local_function_registry.register_service(
        "docker_registry",
        registry_service,
        description="Gestion des registres de conteneurs Docker",
        domains=["docker", "registry", "containers", "images"]
    )

    local_function_registry.register_service(
        "kubernetes",
        k8s_service,
        description="Gestion des clusters et ressources Kubernetes",
        domains=["kubernetes", "k8s", "pods", "deployments", "services"]
    )

    # Créer une nouvelle instance (pas singleton)
    return ChatbotService(
        groq_client=groq_client,
        function_registry=local_function_registry
    )


# === UTILITY FUNCTIONS ===
def reset_chatbot_service():
    """
    Fonction utilitaire pour réinitialiser le service chatbot singleton.
    Utile pour les tests ou en cas de besoin de reset.
    """
    global _chatbot_service_instance
    _chatbot_service_instance = None


def get_chatbot_service_info() -> dict:
    """
    Fonction utilitaire pour obtenir des informations sur l'instance singleton.
    Utile pour le debugging.
    """
    global _chatbot_service_instance
    if _chatbot_service_instance is None:
        return {
            "instance_created": False,
            "pending_actions_count": 0,
            "instance_id": None
        }

    return {
        "instance_created": True,
        "pending_actions_count": len(_chatbot_service_instance.pending_actions),
        "instance_id": id(_chatbot_service_instance),
        "function_registry_services": list(
            _chatbot_service_instance.function_registry.get_available_services_info().keys())
    }