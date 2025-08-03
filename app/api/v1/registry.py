from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.api.schemas.registry import (
    RegistryImagesResponse, ImageFilterRequest, PurgeRequest,
    DetailedImageResponse, PurgeResultResponse, InactiveImageResponse,
    DatabaseStatsResponse, UpdateDescriptionRequest, CleanupRequest, CleanupResponse
)
from app.services.registry_service import RegistryService, logger, ImageFilterCriteria
from app.dependencies import get_registry_service
from app.models.user import User
from app.api.auth import get_current_active_user

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/images", response_model=RegistryImagesResponse)
async def get_registry_images(
        namespace: Optional[str] = None,
        sync_database: bool = True,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Récupère toutes les images avec leur statut de déploiement et synchronise avec la base de données"""
    images = registry_service.get_images_with_deployment_status(namespace, sync_database)

    deployed_count = len([img for img in images if img["is_deployed"]])
    total_deployed_tags = sum(img["deployed_tags_count"] for img in images)

    # Compter les images avec informations DB
    db_sync_count = len([img for img in images if img.get("db_info")])

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
        },
        sync_stats={
            "total_images": len(images),
            "synced_with_db": db_sync_count,
            "sync_enabled": sync_database
        }
    )


@router.get("/catalog")
async def get_registry_catalog(
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
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
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
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
        include_details=filter_request.include_details,
        use_database=filter_request.use_database
    )

    return filtered_images


@router.get("/images/inactive", response_model=List[InactiveImageResponse])
async def get_inactive_images(
        days_since_last_seen: Optional[int] = None,
        include_details: bool = True,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Récupère les images inactives depuis la base de données"""
    inactive_images = registry_service.get_inactive_images_from_db(
        days_since_last_seen=days_since_last_seen,
        include_details=include_details
    )

    return inactive_images


@router.get("/database/stats", response_model=DatabaseStatsResponse)
async def get_database_statistics(
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Récupère les statistiques de la base de données des images"""
    stats = registry_service.get_database_statistics()

    if "error" in stats:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul des statistiques: {stats['error']}")

    return DatabaseStatsResponse(**stats)


@router.put("/images/{image_name}/description")
async def update_image_description(
        image_name: str,
        description_request: UpdateDescriptionRequest,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Met à jour la description d'une image dans la base de données"""
    result = registry_service.update_image_description(
        image_name=image_name,
        description=description_request.description
    )

    if not result["success"]:
        if "non trouvée" in result["message"]:
            raise HTTPException(status_code=404, detail=result["message"])
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    return result


@router.post("/database/cleanup", response_model=CleanupResponse)
async def cleanup_inactive_images(
        cleanup_request: CleanupRequest,
        user_confirmed: bool = False,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Nettoie les images inactives de la base de données"""
    result = registry_service.cleanup_inactive_images(
        older_than_days=cleanup_request.older_than_days,
        dry_run=cleanup_request.dry_run,
        user_confirmed=user_confirmed
    )

    return CleanupResponse(**result)


@router.post("/images/purge", response_model=PurgeResultResponse)
async def purge_images(
        purge_request: PurgeRequest,
        user_confirmed: bool = False,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
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
        dry_run=purge_request.dry_run,
        user_confirmed=user_confirmed
    )

    return purge_results


@router.get("/images/{image_name}/tags/{tag}/details")
async def get_image_tag_details(
        image_name: str,
        tag: str,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Récupère les détails d'un tag d'image spécifique avec informations de la base de données"""

    details = registry_service.get_image_details(image_name, tag)

    if not details:
        raise HTTPException(status_code=404, detail="Image tag not found")

    return details


@router.delete("/images/{image_name}/tags/{tag}")
async def delete_image_tag(
        image_name: str,
        tag: str,
        user_confirmed: bool = False,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Supprime un tag d'image spécifique"""

    success = registry_service.delete_image_tag(
        image_name,
        tag,
        user_confirmed=user_confirmed
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete image tag")

    return {"message": f"Successfully deleted {image_name}:{tag}"}


@router.delete("/images/{image_name}")
async def delete_entire_image(
        image_name: str,
        user_confirmed: bool = False,
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Supprime une image complète (tous ses tags) et met à jour la base de données"""

    result = registry_service.delete_entire_image(
        image_name,
        user_confirmed=user_confirmed
    )

    if not result["success"]:
        if "deployed tags" in result["message"]:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete image {image_name}: {result['message']}"
            )
        elif "not found" in result["message"]:
            raise HTTPException(
                status_code=404,
                detail=result["message"]
            )
        else:
            # Log the full result for debugging
            logger.error(f"Image deletion failed for {image_name}: {result}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete image {image_name}: {result['message']}"
            )

    # Success response with potential warning
    response_data = {
        "message": result["message"],
        "deleted_tags": result["deleted_tags"],
        "verification_passed": result.get("verification_passed", False),
        "database_updated": result.get("database_updated", False)
    }

    # Include warning if present
    if "warning" in result:
        response_data["warning"] = result["warning"]

    # Include any non-critical errors
    if result.get("errors"):
        response_data["errors"] = result["errors"]

    return response_data


@router.post("/sync")
async def force_sync_database(
        registry_service: RegistryService = Depends(get_registry_service),
        current_user: User = Depends(get_current_active_user)
):
    """Force la synchronisation complète avec la base de données"""
    try:
        # Récupérer toutes les images et forcer la synchronisation
        images = registry_service.get_images_with_deployment_status(sync_database=True)

        # Obtenir les statistiques après synchronisation
        stats = registry_service.get_database_statistics()

        return {
            "success": True,
            "message": "✅ Synchronisation complétée avec succès",
            "images_processed": len(images),
            "database_stats": stats,
            "timestamp": stats.get("last_sync")
        }

    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation forcée: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la synchronisation: {str(e)}"
        )