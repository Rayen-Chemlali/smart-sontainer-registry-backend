from fastapi import APIRouter, Depends
from typing import List, Optional
from app.api.schemas.registry import RegistryImagesResponse
from app.services.registry_service import RegistryService
from app.dependencies import get_registry_service
from app.api.schemas.registry import ImageFilterRequest, PurgeRequest, DetailedImageResponse, PurgeResultResponse
from app.services.registry_service import ImageFilterCriteria
from fastapi import HTTPException

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


@router.post("/images/filter", response_model=List[DetailedImageResponse])
async def filter_images(
        filter_request: ImageFilterRequest,
        registry_service: RegistryService = Depends(get_registry_service)
):
    """Filtre les images selon les critères spécifiés"""

    # Convertir le critère string en enum
    try:
        criteria = ImageFilterCriteria(filter_request.filter_criteria)
    except ValueError:
        criteria = ImageFilterCriteria.ALL

    filtered_images = registry_service.get_filtered_images(
        namespace=filter_request.namespace,
        filter_criteria=criteria,
        days_old=filter_request.days_old,
        size_mb=filter_request.size_mb,
        include_details=filter_request.include_details
    )

    return filtered_images


@router.post("/images/purge", response_model=PurgeResultResponse)
async def purge_images(
        purge_request: PurgeRequest,
        registry_service: RegistryService = Depends(get_registry_service)
):
    """Purge les images selon les critères spécifiés"""

    # Convertir le critère string en enum
    try:
        criteria = ImageFilterCriteria(purge_request.filter_criteria)
    except ValueError:
        criteria = ImageFilterCriteria.NOT_DEPLOYED

    purge_results = registry_service.purge_images(
        namespace=purge_request.namespace,
        filter_criteria=criteria,
        days_old=purge_request.days_old,
        size_mb=purge_request.size_mb,
        dry_run=purge_request.dry_run
    )

    return purge_results


@router.get("/images/{image_name}/tags/{tag}/details")
async def get_image_tag_details(
        image_name: str,
        tag: str,
        registry_service: RegistryService = Depends(get_registry_service)
):
    """Récupère les détails d'un tag d'image spécifique"""

    details = registry_service.registry_client.get_detailed_image_info(image_name, tag)

    if not details:
        raise HTTPException(status_code=404, detail="Image tag not found")

    return details


@router.delete("/images/{image_name}/tags/{tag}")
async def delete_image_tag(
        image_name: str,
        tag: str,
        registry_service: RegistryService = Depends(get_registry_service)
):
    """Supprime un tag d'image spécifique"""

    success = registry_service.registry_client.delete_image_tag(image_name, tag)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete image tag")

    return {"message": f"Successfully deleted {image_name}:{tag}"}