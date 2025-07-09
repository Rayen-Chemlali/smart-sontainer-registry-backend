from fastapi import APIRouter, Depends
from app.services.overview_service import OverviewService
from app.dependencies import get_overview_service

router = APIRouter(prefix="/overview", tags=["overview"])

@router.get("/")
async def get_overview(
    overview_service: OverviewService = Depends(get_overview_service)
):
    """Vue d'ensemble complète du système"""
    return overview_service.get_complete_overview()