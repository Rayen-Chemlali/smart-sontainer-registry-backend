from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.repositories.rule_repository import RuleRepository
from app.models.rule import Rule


class RuleEngine:
    """Moteur de règles pour l'évaluation des images"""

    def __init__(self, db: Session):
        self.db = db
        self.rule_repo = RuleRepository(db)

    def get_active_rules(self) -> List[Rule]:
        """Retourne toutes les règles actives"""
        return self.rule_repo.get_active_rules()

    def get_rule_by_id(self, rule_id: int) -> Optional[Rule]:
        """Retourne une règle par son ID"""
        return self.rule_repo.get_by_id(rule_id)

    def create_rule(self, rule_data: Dict[str, Any]) -> Rule:
        """Crée une nouvelle règle"""
        return self.rule_repo.create(rule_data)

    def update_rule(self, rule_id: int, rule_data: Dict[str, Any]) -> Optional[Rule]:
        """Met à jour une règle"""
        return self.rule_repo.update(rule_id, rule_data)

    def delete_rule(self, rule_id: int) -> bool:
        """Supprime une règle"""
        return self.rule_repo.delete(rule_id)

    def activate_rule(self, rule_id: int) -> bool:
        """Active une règle"""
        return self.rule_repo.activate_rule(rule_id)

    def deactivate_rule(self, rule_id: int) -> bool:
        """Désactive une règle"""
        return self.rule_repo.deactivate_rule(rule_id)

    def evaluate_image(self, image_data: Dict[str, Any]) -> List[int]:
        """Évalue une image contre toutes les règles actives"""
        matching_rules = []

        # Ne pas évaluer les images déployées
        if image_data.get("is_deployed", False):
            return matching_rules

        for rule in self.get_active_rules():
            if self._matches_rule(image_data, rule):
                matching_rules.append(rule.id)

        return matching_rules

    def _matches_rule(self, image_data: Dict[str, Any], rule: Rule) -> bool:
        """Vérifie si une image correspond à une règle"""
        if rule.rule_type == "age_based":
            return self._check_age_rule(image_data, rule.conditions)
        elif rule.rule_type == "count_based":
            return self._check_count_rule(image_data, rule.conditions)
        elif rule.rule_type == "tag_based":
            return self._check_tag_rule(image_data, rule.conditions)
        elif rule.rule_type == "size_based":
            return self._check_size_rule(image_data, rule.conditions)
        return False

    def _check_age_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur l'âge"""
        try:
            max_age_days = conditions.get("max_age_days", 30)
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)

            created_at = image_data.get("created_at")
            if not created_at:
                return False

            if isinstance(created_at, str):
                created_at = created_at.replace('Z', '+00:00')
                if '.' in created_at and '+' not in created_at:
                    created_at = created_at.split('.')[0]
                try:
                    image_date = datetime.fromisoformat(created_at)
                except ValueError:
                    image_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S")
            else:
                image_date = created_at

            return image_date < cutoff_date
        except Exception:
            return False

    def _check_count_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur le nombre d'images à garder"""
        keep_count = conditions.get("keep_count", 10)
        image_rank = image_data.get("rank", 0)
        return image_rank > keep_count

    def _check_tag_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur les tags"""
        try:
            image_tags = image_data.get("tags", [])
            if not image_tags:
                tag = image_data.get("tag", "")
                if tag:
                    image_tags = [tag]

            excluded_tags = conditions.get("exclude_tags", [])
            if any(tag in excluded_tags for tag in image_tags):
                return False

            tag_patterns = conditions.get("tag_patterns", [])
            if tag_patterns:
                for tag in image_tags:
                    tag_str = str(tag).lower()
                    for pattern in tag_patterns:
                        if str(pattern).lower() in tag_str:
                            return True
                return False

            return True
        except Exception:
            return False

    def _check_size_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur la taille"""
        try:
            max_size_mb = conditions.get("max_size_mb", 1000)
            max_size_bytes = max_size_mb * 1024 * 1024
            image_size = image_data.get("size", 0)
            return image_size > max_size_bytes
        except Exception:
            return False

    def initialize_default_rules(self) -> List[Rule]:
        """Initialise les règles par défaut si elles n'existent pas"""
        if not self.get_active_rules():
            return self.rule_repo.create_default_rules()
        return []