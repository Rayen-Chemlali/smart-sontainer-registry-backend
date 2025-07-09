from fastapi import APIRouter, Depends
from typing import List, Optional
from app.api.schemas.registry import RegistryImagesResponse
from app.services.registry_service import RegistryService
from app.dependencies import get_registry_service

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/images", response_model=RegistryImagesResponse)
async def get_registry_images(
        namespace: Optional[str] = None,
        registry_service: RegistryService = Depends(get_registry_service)
):
    """Récupère toutes les images avec leur statut de déploiement"""
    images = registry_service.get_images_with_deployment_status(namespace)

    deployed_count = len([img for img in images if img["is_deployed"]])
    total_deployed_tags = sum(img["deployed_tags_count"] for img in images)

    return RegistryImagesResponse(
        namespace=namespace,
        images=images,
        count=len(images),
        deployed_count=deployed_count,
        total_tags=sum(img["tag_count"] for img in images),
        total_deployed_tags=total_deployed_tags,
        raw_deployed_images=[],  # À remplir si nécessaire
        deployment_stats={
            "deployed_images": deployed_count,
            "not_deployed_images": len(images) - deployed_count,
            "deployment_rate": f"{(deployed_count / len(images) * 100):.1f}%" if images else "0%"
        }
    )


@router.get("/catalog")
async def get_registry_catalog(
        registry_service: RegistryService = Depends(get_registry_service)
):
    """Récupère le catalogue du registry"""
    catalog = registry_service.get_catalog()
    return {
        "repositories": catalog,
        "count": len(catalog)
    }