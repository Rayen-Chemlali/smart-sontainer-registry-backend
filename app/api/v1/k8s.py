from fastapi import APIRouter, Depends
from typing import List, Optional
from app.api.schemas.k8s import (
    PodListResponse,
    DeploymentListResponse,
    NamespaceResponse,
    ServiceListResponse,
    DeployedImagesResponse,
    ClusterOverviewResponse,
    ImageSearchResponse
)
from app.services.k8s_service import K8sService
from app.dependencies import get_k8s_service
from app.api.auth import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/k8s", tags=["kubernetes"])

@router.get("/namespaces", response_model=List[NamespaceResponse])
async def get_namespaces(
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Récupère la liste des namespaces"""
    return k8s_service.get_namespaces()

@router.get("/deployed-images", response_model=DeployedImagesResponse)
async def get_deployed_images(
    namespace: Optional[str] = None,
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Récupère les images déployées avec métadonnées"""
    return k8s_service.get_deployed_images(namespace)

@router.get("/pods", response_model=PodListResponse)
async def get_pods(
    namespace: str = "default",
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Récupère les pods avec métadonnées détaillées"""
    return k8s_service.get_pods(namespace)

@router.get("/deployments", response_model=DeploymentListResponse)
async def get_deployments(
    namespace: str = "default",
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Récupère les deployments avec métadonnées détaillées"""
    return k8s_service.get_deployments(namespace)

@router.get("/services", response_model=ServiceListResponse)
async def get_services(
    namespace: str = "default",
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Récupère les services avec métadonnées détaillées"""
    return k8s_service.get_services(namespace)

@router.get("/cluster/overview", response_model=ClusterOverviewResponse)
async def get_cluster_overview(
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Récupère une vue d'ensemble complète du cluster"""
    return k8s_service.get_cluster_overview()

@router.get("/search/image", response_model=ImageSearchResponse)
async def search_resources_by_image(
    image_name: str,
    namespace: Optional[str] = None,
    k8s_service: K8sService = Depends(get_k8s_service),
    current_user: User = Depends(get_current_active_user)
):
    """Recherche tous les pods et deployments utilisant une image spécifique"""
    return k8s_service.search_resources_by_image(image_name, namespace)