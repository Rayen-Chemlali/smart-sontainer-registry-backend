from fastapi import APIRouter, Depends
from typing import List, Optional
from app.api.schemas.k8s import PodResponse, DeploymentResponse, NamespaceResponse
from app.services.k8s_service import K8sService
from app.dependencies import get_k8s_service

router = APIRouter(prefix="/k8s", tags=["kubernetes"])

@router.get("/namespaces", response_model=List[NamespaceResponse])
async def get_namespaces(
    k8s_service: K8sService = Depends(get_k8s_service)
):
    """Récupère la liste des namespaces"""
    return k8s_service.get_namespaces()

@router.get("/deployed-images")
async def get_deployed_images(
    namespace: Optional[str] = None,
    k8s_service: K8sService = Depends(get_k8s_service)
):
    """Récupère les images déployées"""
    deployed_images = k8s_service.get_deployed_images(namespace)
    return {
        "namespace": namespace or "all",
        "deployed_images": list(deployed_images),
        "count": len(deployed_images)
    }

@router.get("/pods", response_model=List[PodResponse])
async def get_pods(
    namespace: str = "default",
    k8s_service: K8sService = Depends(get_k8s_service)
):
    """Récupère les pods"""
    return k8s_service.get_pods(namespace)

@router.get("/deployments", response_model=List[DeploymentResponse])
async def get_deployments(
    namespace: str = "default",
    k8s_service: K8sService = Depends(get_k8s_service)
):
    """Récupère les deployments"""
    return k8s_service.get_deployments(namespace)