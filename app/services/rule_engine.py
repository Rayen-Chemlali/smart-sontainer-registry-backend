from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.repositories.rule_repository import RuleRepository
from app.models.rule import Rule
import logging
from app.core.decorators import chatbot_function

logger = logging.getLogger(__name__)


class RuleDict(dict):
    def __getattr__(self, key):
        return self[key]


class RuleEngine:
    """Moteur de règles pour l'évaluation des images"""

    def __init__(self, db: Session):
        self.db = db
        self.rule_repo = RuleRepository(db)

    def _rule_to_dict(self, rule: Rule) -> Dict[str, Any]:
        """Convertit un objet Rule en dictionnaire sérialisable JSON"""
        return RuleDict({
            "id": rule.id,
            "name": rule.name,
            "rule_type": rule.rule_type,
            "description": rule.description or "Aucune description",
            "conditions": rule.conditions or {},
            "action": rule.action or "unknown",
            "is_active": rule.is_active,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None
        })

    @chatbot_function(
        name="get_active_rules",
        description="Récupère toutes les règles actives du moteur de règles pour l'évaluation des images",
        examples=[
            "Quelles sont les règles actives ?",
            "Montre-moi les règles en cours",
            "Liste des règles de nettoyage activées"
        ]
    )
    def get_active_rules(self) -> List[Dict[str, Any]]:
        """Retourne toutes les règles actives sous forme de dictionnaires sérialisables"""
        try:
            rules = self.rule_repo.get_active_rules()
            serialized_rules = [self._rule_to_dict(rule) for rule in rules]
            logger.info(f"Récupération de {len(serialized_rules)} règles actives")
            return serialized_rules
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des règles actives: {str(e)}")
            return [{
                "error": f"Erreur lors de la récupération des règles: {str(e)}",
                "rules_count": 0,
                "timestamp": datetime.utcnow().isoformat()
            }]

    def get_rule_by_id(self, rule_id: int) -> Optional[Rule]:
        """Retourne une règle par son ID"""
        return self.rule_repo.get_by_id(rule_id)

    @chatbot_function(
        name="create_rule",
        description="Crée une nouvelle règle de nettoyage d'images avec des conditions spécifiques",
        parameters_schema={
            "rule_data": {
                "type": "dict",
                "required": True,
                "description": "Données de la règle (name, rule_type, conditions, action, description)"
            }
        },
        examples=[
            "Crée une règle pour supprimer les images de plus de 30 jours",
            "Ajoute une règle basée sur la taille des images",
            "Nouvelle règle pour les tags de développement"
        ]
    )
    def create_rule(self, rule_data: Dict[str, Any]) -> Rule:
        """Crée une nouvelle règle"""
        return self.rule_repo.create(rule_data)

    @chatbot_function(
        name="update_rule",
        description="Met à jour une règle existante avec de nouvelles conditions ou paramètres",
        parameters_schema={
            "rule_id": {
                "type": "int",
                "required": True,
                "description": "ID de la règle à modifier"
            },
            "rule_data": {
                "type": "dict",
                "required": True,
                "description": "Nouvelles données de la règle"
            }
        },
        examples=[
            "Modifie la règle 1 pour changer la limite d'âge",
            "Update la règle de taille maximale",
            "Change les conditions de la règle de tags"
        ]
    )
    def update_rule(self, rule_id: int, rule_data: Dict[str, Any]) -> Optional[Rule]:
        """Met à jour une règle"""
        return self.rule_repo.update(rule_id, rule_data)

    def delete_rule(self, rule_id: int) -> bool:
        """Supprime une règle"""
        return self.rule_repo.delete(rule_id)

    @chatbot_function(
        name="activate_rule",
        description="Active une règle désactivée pour qu'elle soit prise en compte dans les évaluations",
        parameters_schema={
            "rule_id": {
                "type": "int",
                "required": True,
                "description": "ID de la règle à activer"
            }
        },
        examples=[
            "Active la règle 3",
            "Réactive la règle de nettoyage des vieilles images",
            "Remets en service la règle ID 1"
        ]
    )
    def activate_rule(self, rule_id: int) -> bool:
        """Active une règle"""
        return self.rule_repo.activate_rule(rule_id)

    @chatbot_function(
        name="deactivate_rule",
        description="Désactive une règle active pour qu'elle ne soit plus appliquée lors des évaluations",
        parameters_schema={
            "rule_id": {
                "type": "int",
                "required": True,
                "description": "ID de la règle à désactiver"
            }
        },
        examples=[
            "Désactive la règle 2",
            "Arrête temporairement la règle de taille",
            "Mets en pause la règle ID 5"
        ]
    )
    def deactivate_rule(self, rule_id: int) -> bool:
        """Désactive une règle"""
        return self.rule_repo.deactivate_rule(rule_id)

    @chatbot_function(
        name="evaluate_image",
        description="Évalue une image contre toutes les règles actives et retourne les règles correspondantes",
        parameters_schema={
            "image_data": {
                "type": "dict",
                "required": True,
                "description": "Données de l'image à évaluer (name, tags, created_at, size, etc.)"
            }
        },
        examples=[
            "Évalue cette image contre les règles",
            "Vérifie si l'image correspond aux critères de suppression",
            "Analyse l'image selon les règles actives"
        ]
    )
    def evaluate_image(self, image_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Évalue une image contre toutes les règles actives"""
        matching_rules = []

        if image_data.get("is_deployed", False):
            logger.debug(f"Skipping deployed image: {image_data.get('name', 'unknown')}")
            return matching_rules

        active_rules = self.get_active_rules()
        logger.debug(f"Evaluating image {image_data.get('name', 'unknown')} against {len(active_rules)} rules")

        for rule in active_rules:
            try:
                if self._matches_rule(image_data, rule):
                    rule_match = {
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "rule_type": rule.rule_type,
                        "description": rule.description,
                        "action": rule.action,
                        "conditions": rule.conditions,
                        "match_details": self._get_match_details(image_data, rule)
                    }
                    matching_rules.append(rule_match)
                    logger.debug(f"Image {image_data.get('name')} matches rule {rule.name}")
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.id} ({rule.name}): {str(e)}")
                continue

        return matching_rules

    def _get_match_details(self, image_data: Dict[str, Any], rule: Rule) -> Dict[str, Any]:
        """Obtient les détails du match pour debug/info"""
        details = {
            "rule_type": rule.rule_type,
            "image_name": image_data.get("name", "unknown")
        }

        try:
            if rule.rule_type.lower() == "age_based":
                created_at = image_data.get("created_at")
                max_age_days = rule.conditions.get("max_age_days", 30)
                details.update({
                    "image_created_at": created_at,
                    "max_age_days": max_age_days,
                    "reason": f"Image older than {max_age_days} days"
                })

            elif rule.rule_type.lower() == "tag_based":
                image_tags = image_data.get("tags", [])
                details.update({
                    "image_tags": image_tags,
                    "required_patterns": rule.conditions.get("required_patterns", []),
                    "exclude_tags": rule.conditions.get("exclude_tags", []),
                    "reason": "Tag pattern matched"
                })

            elif rule.rule_type.lower() == "size_based":
                image_size = image_data.get("size", 0)
                max_size_mb = rule.conditions.get("max_size_mb", 1000)
                details.update({
                    "image_size_bytes": image_size,
                    "max_size_mb": max_size_mb,
                    "reason": f"Image larger than {max_size_mb}MB"
                })

        except Exception as e:
            details["error"] = str(e)

        return details

    def evaluate_images_batch(self, images_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Évalue un lot d'images contre toutes les règles actives"""
        results = {}
        active_rules = self.get_active_rules()

        if not active_rules:
            logger.warning("No active rules found for batch evaluation")
            return results

        for image_data in images_data:
            image_key = f"{image_data.get('name', 'unknown')}:{image_data.get('tag', 'latest')}"
            results[image_key] = self.evaluate_image(image_data)

        return results

    def _matches_rule(self, image_data: Dict[str, Any], rule: Rule) -> bool:
        """Vérifie si une image correspond à une règle"""
        rule_type = rule.rule_type.lower()

        if rule_type == "age_based":
            return self._check_age_rule(image_data, rule.conditions)
        elif rule_type == "count_based":
            return self._check_count_rule(image_data, rule.conditions)
        elif rule_type == "tag_based":
            return self._check_tag_rule(image_data, rule.conditions)
        elif rule_type == "size_based":
            return self._check_size_rule(image_data, rule.conditions)
        elif rule_type == "modified_based":
            return self._check_modified_rule(image_data, rule.conditions)
        else:
            logger.warning(f"Unknown rule type: {rule_type}")
            return False

    def _check_age_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur l'âge (date de création)"""
        try:
            max_age_days = conditions.get("max_age_days", 30)
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)

            created_at = (image_data.get("created_at") or
                          image_data.get("created") or
                          image_data.get("creation_date"))

            if not created_at:
                logger.debug(f"No creation date found for image {image_data.get('name')}")
                return False

            image_date = self._parse_date(created_at)
            if not image_date:
                return False

            if image_date.tzinfo is None:
                image_date = image_date.replace(tzinfo=None)
                cutoff_date = cutoff_date.replace(tzinfo=None)

            result = image_date < cutoff_date
            logger.debug(f"Age rule check: {image_date} < {cutoff_date} = {result}")
            return result

        except Exception as e:
            logger.error(f"Error in age rule check: {str(e)}")
            return False

    def _check_modified_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur la date de dernière modification"""
        try:
            max_age_days = conditions.get("max_age_days", 30)
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)

            modified_at = (image_data.get("last_modified") or
                           image_data.get("modified_at") or
                           image_data.get("updated_at"))

            if not modified_at:
                logger.debug(f"No modification date found for image {image_data.get('name')}")
                return False

            image_date = self._parse_date(modified_at)
            if not image_date:
                return False

            if image_date.tzinfo is None:
                image_date = image_date.replace(tzinfo=None)
                cutoff_date = cutoff_date.replace(tzinfo=None)

            result = image_date < cutoff_date
            logger.debug(f"Modified rule check: {image_date} < {cutoff_date} = {result}")
            return result

        except Exception as e:
            logger.error(f"Error in modified rule check: {str(e)}")
            return False

    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """Parse une date depuis différents formats"""
        if not date_str:
            return None

        if isinstance(date_str, datetime):
            return date_str

        if not isinstance(date_str, str):
            date_str = str(date_str)

        date_str = date_str.replace('Z', '+00:00')

        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            logger.warning(f"Could not parse date: {date_str}")
            return None

    def _check_count_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur le nombre d'images à garder"""
        try:
            keep_count = conditions.get("keep_count", 10)
            image_rank = image_data.get("rank", 0)

            if image_rank == 0:
                logger.debug("Image rank not set, skipping count rule")
                return False

            result = image_rank > keep_count
            logger.debug(f"Count rule check: rank {image_rank} > keep {keep_count} = {result}")
            return result

        except Exception as e:
            logger.error(f"Error in count rule check: {str(e)}")
            return False

    def _check_tag_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur les tags"""
        try:
            image_tags = image_data.get("tags", [])
            if not image_tags:
                tag = image_data.get("tag", "")
                if tag:
                    image_tags = [tag]

            if not image_tags:
                logger.debug("No tags found for image")
                return False

            excluded_tags = conditions.get("exclude_tags", [])
            if excluded_tags:
                for tag in image_tags:
                    tag_str = str(tag).lower()
                    for excluded in excluded_tags:
                        if str(excluded).lower() in tag_str:
                            logger.debug(f"Tag {tag} matches excluded pattern {excluded}")
                            return False

            required_patterns = conditions.get("required_patterns", [])
            if required_patterns:
                for tag in image_tags:
                    tag_str = str(tag).lower()
                    for pattern in required_patterns:
                        if str(pattern).lower() in tag_str:
                            logger.debug(f"Tag {tag} matches required pattern {pattern}")
                            return True
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

        except Exception as e:
            logger.error(f"Error in tag rule check: {str(e)}")
            return False

    def _check_size_rule(self, image_data: Dict[str, Any], conditions: Dict) -> bool:
        """Règle basée sur la taille"""
        try:
            max_size_mb = conditions.get("max_size_mb", 1000)
            max_size_bytes = max_size_mb * 1024 * 1024
            image_size = image_data.get("size", 0)

            if image_size == 0:
                logger.debug("Image size not available")
                return False

            result = image_size > max_size_bytes
            logger.debug(f"Size rule check: {image_size} bytes > {max_size_bytes} bytes = {result}")
            return result

        except Exception as e:
            logger.error(f"Error in size rule check: {str(e)}")
            return False

    @chatbot_function(
        name="get_rule_statistics",
        description="Retourne des statistiques détaillées sur toutes les règles (actives, inactives, par type, par action)",
        examples=[
            "Statistiques des règles",
            "Combien de règles sont actives ?",
            "Résumé des règles par type et action"
        ]
    )
    def get_rule_statistics(self) -> Dict[str, Any]:
        """Retourne des statistiques sur les règles"""
        try:
            all_rules = self.rule_repo.get_all()
            active_rules = self.get_active_rules()

            stats = {
                "total_rules": len(all_rules),
                "active_rules": len(active_rules),
                "inactive_rules": len(all_rules) - len(active_rules),
                "rules_by_type": {},
                "rules_by_action": {}
            }

            for rule in all_rules:
                rule_type = rule.rule_type
                if rule_type not in stats["rules_by_type"]:
                    stats["rules_by_type"][rule_type] = {"total": 0, "active": 0}
                stats["rules_by_type"][rule_type]["total"] += 1
                if rule.is_active:
                    stats["rules_by_type"][rule_type]["active"] += 1

                action = rule.action
                if action not in stats["rules_by_action"]:
                    stats["rules_by_action"][action] = {"total": 0, "active": 0}
                stats["rules_by_action"][action]["total"] += 1
                if rule.is_active:
                    stats["rules_by_action"][action]["active"] += 1

            return stats

        except Exception as e:
            logger.error(f"Error getting rule statistics: {str(e)}")
            return {"error": str(e)}

    def initialize_default_rules(self) -> List[Rule]:
        """Initialise les règles par défaut si elles n'existent pas"""
        try:
            if not self.get_active_rules():
                logger.info("No active rules found, creating default rules")
                return self.rule_repo.create_default_rules()
            return []
        except Exception as e:
            logger.error(f"Error initializing default rules: {str(e)}")
            return []