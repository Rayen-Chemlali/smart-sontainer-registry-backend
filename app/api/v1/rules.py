from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, validator
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.rule_engine import RuleEngine
from app.models.user import User
from app.dependencies import get_rule_evaluation_worker
from app.core.database import get_db
from app.api.auth import require_admin

router = APIRouter(prefix="/rules", tags=["rules"])


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


def get_rule_engine(db: Session = Depends(get_db)) -> RuleEngine:
    return RuleEngine(db)


# ========== CRUD RULES ==========
@router.post("/", response_model=RuleResponse)
async def create_rule(
        rule_data: RuleCreate,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Créer une nouvelle règle"""
    rule_dict = {
        "name": rule_data.name,
        "rule_type": rule_data.rule_type,
        "description": rule_data.description,
        "conditions": rule_data.conditions,
        "is_active": True
    }
    created_rule = rule_engine.create_rule(rule_dict)
    return RuleResponse.from_orm(created_rule)


@router.get("/", response_model=List[RuleResponse])
async def get_rules(
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Obtenir toutes les règles"""
    rules = rule_engine.get_active_rules()
    return [RuleResponse.from_orm(rule) for rule in rules]


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
        rule_id: int,
        rule_data: RuleCreate,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Mettre à jour une règle"""
    rule_dict = {
        "name": rule_data.name,
        "rule_type": rule_data.rule_type,
        "description": rule_data.description,
        "conditions": rule_data.conditions
    }
    updated_rule = rule_engine.update_rule(rule_id, rule_dict)
    if not updated_rule:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return RuleResponse.from_orm(updated_rule)


@router.delete("/{rule_id}")
async def delete_rule(
        rule_id: int,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Supprimer une règle"""
    success = rule_engine.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return {"message": "Règle supprimée avec succès"}


@router.post("/{rule_id}/activate")
async def activate_rule(
        rule_id: int,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Activer une règle"""
    success = rule_engine.activate_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return {"message": "Règle activée avec succès"}


@router.post("/{rule_id}/deactivate")
async def deactivate_rule(
        rule_id: int,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Désactiver une règle"""
    success = rule_engine.deactivate_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return {"message": "Règle désactivée avec succès"}


# ========== EVALUATION ==========
@router.post("/evaluate", response_model=EvaluationResult)
async def trigger_evaluation(
        current_user: User = Depends(require_admin)
):
    """Déclencher l'évaluation et retourner le résumé"""
    worker = get_rule_evaluation_worker()
    try:
        results = await worker.evaluate_all_images()

        return EvaluationResult(
            timestamp=results["timestamp"],
            total_images_scanned=results["summary"]["total_images_scanned"],
            matching_images_count=results["summary"]["matching_images_count"],
            non_matching_images_count=results["summary"]["non_matching_images_count"],
            deployed_images_skipped=results["summary"]["deployed_images_skipped"],
            errors_count=results["summary"]["errors_count"],
            duration_seconds=results["evaluation_stats"]["evaluation_duration_seconds"],
            rules_applied=results["evaluation_stats"]["rules_applied"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'évaluation: {str(e)}")


@router.get("/matching-images", response_model=List[MatchingImage])
async def get_matching_images(
        current_user: User = Depends(require_admin)
):
    """Obtenir les images qui peuvent être supprimées"""
    worker = get_rule_evaluation_worker()
    results = worker.get_last_evaluation_results()

    if not results.get("timestamp"):
        raise HTTPException(status_code=404, detail="Aucun résultat d'évaluation disponible")

    matching_images = []
    for img_result in results.get("matching_images", []):
        image_data = img_result["image"]
        matching_images.append(MatchingImage(
            image_name=image_data["image_name"],
            tag=image_data["tag"],
            size=image_data.get("size", 0),
            created_at=image_data.get("created_at", ""),
            matching_rules=img_result["matching_rules"],
            is_deployed=image_data.get("is_deployed", False)
        ))

    return matching_images


# ========== UTILITY ==========
@router.post("/initialize-default")
async def initialize_default_rules(
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Initialiser les règles par défaut"""
    created_rules = rule_engine.initialize_default_rules()
    return {
        "message": f"{len(created_rules)} règles par défaut créées",
        "rules": [RuleResponse.from_orm(rule) for rule in created_rules]
    }