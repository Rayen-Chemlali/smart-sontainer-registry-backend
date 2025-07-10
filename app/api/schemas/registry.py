from pydantic import BaseModel
from typing import List, Optional, Dict


class ImageResponse(BaseModel):
    name: str
    tags: List[str]
    tag_count: int
    is_deployed: bool
    deployed_tags: List[str]
    deployed_tags_count: int

class RegistryImagesResponse(BaseModel):
    namespace: Optional[str]
    images: List[ImageResponse]
    count: int
    deployed_count: int
    total_tags: int
    total_deployed_tags: int
    raw_deployed_images: List[str]
    deployment_stats: dict
class ImageFilterRequest(BaseModel):
    namespace: Optional[str] = None
    filter_criteria: str = "all"  # all, deployed, not_deployed, older_than, larger_than, unused_tags
    days_old: int = 30
    size_mb: int = 100
    include_details: bool = False

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

class PurgeResultResponse(BaseModel):
    dry_run: bool
    total_images_evaluated: int
    images_to_delete: List[Dict]
    tags_to_delete: List[Dict]
    estimated_space_freed: int
    errors: List[str]