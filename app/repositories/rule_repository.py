from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.repositories.base_repository import BaseRepository


class RuleRepository(BaseRepository[Rule]):
    """Repository pour la gestion des règles de suppression"""

    def __init__(self, db: Session):
        super().__init__(Rule, db)

    def get_active_rules(self) -> List[Rule]:
        """Récupère toutes les règles actives"""
        return self.db.query(Rule).filter(Rule.is_active == True).all()

    def get_by_name(self, name: str) -> Optional[Rule]:
        """Récupère une règle par son nom"""
        return self.get_by_field("name", name)

    def get_by_type(self, rule_type: str) -> List[Rule]:
        """Récupère les règles par type"""
        return self.get_many_by_field("rule_type", rule_type)

    def activate_rule(self, rule_id: int) -> bool:
        """Active une règle"""
        return bool(self.update(rule_id, {"is_active": True}))

    def deactivate_rule(self, rule_id: int) -> bool:
        """Désactive une règle"""
        return bool(self.update(rule_id, {"is_active": False}))

    def create_default_rules(self) -> List[Rule]:
        """Crée les règles par défaut"""
        default_rules = [
            {
                "name": "Images plus anciennes que 30 jours",
                "rule_type": "age_based",
                "description": "Supprime les images non déployées plus anciennes que 30 jours",
                "conditions": {"max_age_days": 30},
                "action": "delete",
                "is_active": True
            },
            {
                "name": "Tags de développement",
                "rule_type": "tag_based",
                "description": "Supprime les tags de développement anciens",
                "conditions": {
                    "tag_patterns": ["dev", "test", "staging"],
                    "exclude_tags": ["latest", "prod", "production"]
                },
                "action": "delete",
                "is_active": True
            },
            {
                "name": "Images volumineuses",
                "rule_type": "size_based",
                "description": "Supprime les images plus grandes que 1GB",
                "conditions": {"max_size_mb": 1024},
                "action": "delete",
                "is_active": False
            }
        ]

        return self.bulk_create(default_rules)