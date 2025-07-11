from functools import lru_cache
from app.external.s3_client import S3Client
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
from app.external.groq_client import GroqClient
from app.services.registry_service import RegistryService
from app.services.k8s_service import K8sService
from app.services.overview_service import OverviewService
from app.services.chatbot_service import ChatbotService
from app.config import settings

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
    return RegistryClient(settings.REGISTRY_URL)

@lru_cache()
def get_k8s_client() -> K8sClient:
    return K8sClient()

@lru_cache()
def get_groq_client() -> GroqClient:
    return GroqClient(settings.GROQ_API_KEY)

def get_registry_service() -> RegistryService:
    return RegistryService(get_registry_client(), get_k8s_client())

def get_k8s_service() -> K8sService:
    return K8sService(get_k8s_client())

def get_overview_service() -> OverviewService:
    return OverviewService(get_s3_client(), get_registry_service(), get_k8s_service())

def get_chatbot_service() -> ChatbotService:
    return ChatbotService(
        groq_client=get_groq_client(),
        registry_service=get_registry_service(),
        k8s_service=get_k8s_service(),
        overview_service=get_overview_service(),
        s3_client=get_s3_client()
    )