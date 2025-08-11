from pydantic import BaseModel, validator
from datetime import datetime
from typing import List, Dict, Any, Optional

class RuleCreate(BaseModel):
    name: str
    rule_type: str  # age_based, count_based, tag_based, size_based
    description: str
    conditions: Dict[str, Any]


class RuleResponse(BaseModel):
    id: int
    name: str
    rule_type: str
    description: str
    conditions: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EvaluationResult(BaseModel):
    """Résultat simplifié d'évaluation"""
    timestamp: str
    total_images_scanned: int
    matching_images_count: int
    non_matching_images_count: int
    deployed_images_skipped: int
    errors_count: int
    duration_seconds: float
    rules_applied: int


class MatchingImage(BaseModel):
    """Image qui peut être supprimée"""
    image_name: str
    tag: str
    size: int
    created_at: Optional[str]  # Allow None values
    matching_rules: List[Dict[str, Any]]
    is_deployed: bool

    @validator('created_at', pre=True)
    def handle_none_created_at(cls, v):
        """Convert None to empty string"""
        return v if v is not None else ""
