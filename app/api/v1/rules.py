from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.rule_engine import RuleEngine
from app.models.rule import Rule
from app.models.user import User
from app.dependencies import get_rule_evaluation_worker  # FIXED: Import from dependencies
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


class DeletionProposalResponse(BaseModel):
    id: str
    image_name: str
    tag: str
    reason: str
    proposed_at: str
    status: str


def get_rule_engine(db: Session = Depends(get_db)) -> RuleEngine:
    """Récupère l'instance du rule engine avec la session DB"""
    return RuleEngine(db)


@router.post("/", response_model=RuleResponse)
async def create_rule(
        rule_data: RuleCreate,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Créer une nouvelle règle de suppression"""
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
    """Obtenir toutes les règles actives"""
    rules = rule_engine.get_active_rules()
    return [RuleResponse.from_orm(rule) for rule in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
        rule_id: int,
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Obtenir une règle spécifique"""
    rule = rule_engine.get_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Règle non trouvée")

    return RuleResponse.from_orm(rule)


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


@router.post("/evaluate")
async def evaluate_image(
        image_data: Dict[str, Any],
        rule_engine: RuleEngine = Depends(get_rule_engine),
        current_user: User = Depends(require_admin)
):
    """Évaluer une image contre toutes les règles"""
    matching_rules = rule_engine.evaluate_image(image_data)
    return {
        "image": image_data.get("name", "unknown"),
        "matching_rule_ids": matching_rules,
        "should_delete": len(matching_rules) > 0
    }


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


@router.post("/trigger-evaluation")
async def trigger_evaluation(
    current_user: User = Depends(require_admin)
):
    """Déclencher une évaluation manuelle des règles"""
    worker = get_rule_evaluation_worker()  # FIXED: Use the correct function name
    try:
        await worker.evaluate_all_images()
        return {"message": "Évaluation des règles déclenchée avec succès"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'évaluation: {str(e)}")


# Endpoints pour les propositions de suppression
@router.get("/proposals/", response_model=List[DeletionProposalResponse])
async def get_deletion_proposals(
    current_user: User = Depends(require_admin)
):
    """Obtenir toutes les propositions de suppression"""
    worker = get_rule_evaluation_worker()  # FIXED: Use the correct function name
    proposals = worker.get_deletion_proposals()

    return [
        DeletionProposalResponse(
            id=proposal["id"],
            image_name=proposal["image_name"],
            tag=proposal["tag"],
            reason=proposal["reason"],
            proposed_at=proposal["proposed_at"],
            status=proposal["status"]
        )
        for proposal in proposals
    ]


@router.post("/proposals/{proposal_id}/approve")
async def approve_deletion_proposal(
    proposal_id: str,
    current_user: User = Depends(require_admin)
):
    """Approuver une proposition de suppression"""
    worker = get_rule_evaluation_worker()  # FIXED: Use the correct function name
    result = worker.approve_deletion_proposal(proposal_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/proposals/{proposal_id}/reject")
async def reject_deletion_proposal(
    proposal_id: str,
    current_user: User = Depends(require_admin)
):
    """Rejeter une proposition de suppression"""
    worker = get_rule_evaluation_worker()  # FIXED: Use the correct function name
    result = worker.reject_deletion_proposal(proposal_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result