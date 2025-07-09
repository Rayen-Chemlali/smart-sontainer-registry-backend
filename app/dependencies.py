from functools import lru_cache
from app.external.s3_client import S3Client
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
from app.services.registry_service import RegistryService
from app.services.k8s_service import K8sService
from app.services.overview_service import OverviewService
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

def get_registry_service() -> RegistryService:
    return RegistryService(get_registry_client(), get_k8s_client())

def get_k8s_service() -> K8sService:
    return K8sService(get_k8s_client())

def get_overview_service() -> OverviewService:
    return OverviewService(get_s3_client(), get_registry_service(), get_k8s_service())