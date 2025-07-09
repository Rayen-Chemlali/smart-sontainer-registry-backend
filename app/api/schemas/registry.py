from pydantic import BaseModel
from typing import List, Optional

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