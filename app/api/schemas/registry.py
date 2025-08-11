from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class DatabaseInfo(BaseModel):
    id: Optional[int] = None
    is_active: bool = True
    description: Optional[str] = None
    first_detected_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    days_since_last_seen: Optional[int] = None
    in_database: bool = True


class ImageResponse(BaseModel):
    name: str
    tags: List[str]
    tag_count: int
    is_deployed: bool
    deployed_tags: List[str]
    deployed_tags_count: int
    db_info: Optional[DatabaseInfo] = None


class RegistryImagesResponse(BaseModel):
    namespace: Optional[str]
    images: List[ImageResponse]
    count: int
    deployed_count: int
    total_tags: int
    total_deployed_tags: int
    raw_deployed_images: List[str]
    deployment_stats: dict
    sync_stats: Optional[Dict[str, int]] = None


class ImageFilterRequest(BaseModel):
    namespace: Optional[str] = None
    filter_criteria: str = "all"
    days_old: int = 30
    size_mb: int = 100
    include_details: bool = False
    use_database: bool = False


class PurgeRequest(BaseModel):
    namespace: Optional[str] = None
    filter_criteria: str = "not_deployed"
    days_old: int = 30
    size_mb: int = 100
    dry_run: bool = True


class TagDetails(BaseModel):
    tag: str
    size: int
    created: Optional[str]
    is_deployed: bool


class DetailedImageResponse(BaseModel):
    name: str
    tags: List[str]
    tag_count: int
    is_deployed: bool
    deployed_tags: List[str]
    deployed_tags_count: int
    detailed_tags: Optional[List[TagDetails]] = None
    db_info: Optional[DatabaseInfo] = None


class PurgeResultResponse(BaseModel):
    # Champs obligatoires - TOUJOURS présents
    dry_run: bool
    user_confirmed: bool
    total_images_evaluated: int
    images_to_delete: List[Dict[str, Any]]
    tags_to_delete: List[Dict[str, Any]]
    estimated_space_freed: float  # en MB
    errors: List[str]

    # Champs optionnels - pour compatibilité et informations supplémentaires
    preview: Optional[Dict[str, Any]] = None
    images_preview: Optional[List[Dict[str, Any]]] = None
    action_required: Optional[str] = None
    confirmation_message: Optional[str] = None
    execution_summary: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class InactiveImageResponse(BaseModel):
    name: str
    is_active: bool
    is_deployed: bool
    last_seen_at: Optional[str]
    first_detected_at: Optional[str]
    days_since_last_seen: Optional[int]
    description: Optional[str] = None
    total_tags: int = 0
    total_size_mb: float = 0.0
    deployed_tags_count: int = 0


class DatabaseStatsResponse(BaseModel):
    total_images: int
    active_images: int
    inactive_images: int
    deployed_images: int
    recent_images: int
    old_images: int
    activity_rate: str
    deployment_rate: str
    last_sync: str
    sync_recommendation: str


class UpdateDescriptionRequest(BaseModel):
    description: str


class CleanupRequest(BaseModel):
    older_than_days: int = 90
    dry_run: bool = True


class CleanupResponse(BaseModel):
    dry_run: bool
    user_confirmed: bool = False
    images_to_delete: int = 0
    preview: Optional[List[Dict]] = None
    cleanup_completed: bool = False
    deleted_count: int = 0
    deleted_images: Optional[List[str]] = None
    error: Optional[str] = None