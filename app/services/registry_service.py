from typing import List, Dict, Optional, Set, Any
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
from app.repositories.image_repository import ImageRepository
from app.core.decorators import chatbot_function
from datetime import datetime, timedelta
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class ImageFilterCriteria(Enum):
    """Critères de filtrage des images"""
    ALL = "all"
    DEPLOYED = "deployed"
    NOT_DEPLOYED = "not_deployed"
    OLDER_THAN = "older_than"
    MODIFIED_BEFORE = "modified_before"
    LARGER_THAN = "larger_than"
    UNUSED_TAGS = "unused_tags"
    ACTIVE = "active"
    INACTIVE = "inactive"


class RegistryService:
    def __init__(self, registry_client: RegistryClient, k8s_client: K8sClient, image_repository: ImageRepository):
        self.registry_client = registry_client
        self.k8s_client = k8s_client
        self.image_repository = image_repository

    @chatbot_function(
        name="get_images_with_deployment_status",
        description="Récupère toutes les images du registry avec leur statut de déploiement Kubernetes et les synchronise avec la base de données",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "description": "Namespace Kubernetes spécifique à analyser (optionnel)"
            },
            "sync_database": {
                "type": "bool",
                "required": False,
                "description": "Synchroniser les données avec la base de données (défaut: True)"
            }
        },
        examples=[
            "Affiche-moi toutes les images avec leur statut de déploiement",
            "Quelles images sont déployées dans le namespace production ?",
            "Liste les images du registry avec leurs tags déployés et synchronise la base"
        ]
    )
    def get_images_with_deployment_status(self, namespace: Optional[str] = None, sync_database: bool = True) -> List[
        Dict]:
        """Récupère toutes les images avec leur statut de déploiement et tous les détails"""
        # Récupérer les images déployées
        deployed_images = self.k8s_client.get_deployed_images(namespace)

        # Récupérer le catalogue du registry
        catalog = self.registry_client.get_catalog()
        images = []

        # Normaliser les images déployées pour la comparaison
        normalized_deployed = {}
        for deployed_img in deployed_images:
            name, tag = self.registry_client.extract_name_and_tag(deployed_img)
            if name not in normalized_deployed:
                normalized_deployed[name] = set()
            normalized_deployed[name].add(tag)
            logger.info(f"Image déployée détectée: {name}:{tag} (original: {deployed_img})")

        for image_name in catalog:
            tags = self.registry_client.get_image_tags(image_name)

            # Vérifier si l'image est déployée
            is_deployed = image_name in normalized_deployed

            # Déterminer quels tags sont déployés
            deployed_tags = []
            if is_deployed:
                deployed_tags = list(normalized_deployed[image_name].intersection(set(tags)))
                # Aussi vérifier si 'latest' est utilisé implicitement
                if 'latest' in normalized_deployed[image_name] and 'latest' not in tags:
                    if tags:
                        deployed_tags.append(tags[0])

            # Récupérer les détails complets de chaque tag
            detailed_tags = []
            total_size = 0

            for tag in tags:
                try:
                    # Récupérer tous les détails du tag
                    tag_details = self.registry_client.get_detailed_image_info(image_name, tag)

                    tag_info = {
                        "tag": tag,
                        "size": tag_details.get("size", 0),
                        "size_mb": round(tag_details.get("size", 0) / (1024 * 1024), 2),
                        "created": tag_details.get("created"),
                        "last_modified": tag_details.get("last_modified"),
                        "digest": tag_details.get("digest"),
                        "layers": tag_details.get("layers", []),
                        "layer_count": len(tag_details.get("layers", [])),
                        "config": tag_details.get("config", {}),
                        "architecture": tag_details.get("architecture"),
                        "os": tag_details.get("os"),
                        "is_deployed": tag in deployed_tags
                    }

                    detailed_tags.append(tag_info)
                    total_size += tag_details.get("size", 0)

                except Exception as e:
                    logger.warning(f"Impossible de récupérer les détails pour {image_name}:{tag}: {e}")
                    # Tag avec détails par défaut en cas d'erreur
                    detailed_tags.append({
                        "tag": tag,
                        "size": 0,
                        "size_mb": 0,
                        "created": None,
                        "last_modified": None,
                        "digest": None,
                        "layers": [],
                        "layer_count": 0,
                        "config": {},
                        "architecture": None,
                        "os": None,
                        "is_deployed": tag in deployed_tags,
                        "error": str(e)
                    })

            image_data = {
                "name": image_name,
                "tags": tags,
                "tag_count": len(tags),
                "is_deployed": is_deployed,
                "deployed_tags": deployed_tags,
                "deployed_tags_count": len(deployed_tags),
                "detailed_tags": detailed_tags,
                "total_size": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }

            images.append(image_data)

        # Synchronisation avec la base de données
        if sync_database:
            try:
                sync_stats = self.image_repository.bulk_sync_images(images)
                logger.info(f"Synchronisation DB terminée: {sync_stats}")

                # Ajouter les informations de la DB aux images si disponibles
                for image in images:
                    db_image = self.image_repository.get_by_name(image["name"])
                    if db_image:
                        image["db_info"] = {
                            "id": db_image.id,
                            "is_active": db_image.is_active,
                            "first_detected_at": db_image.first_detected_at.isoformat() if db_image.first_detected_at else None,
                            "last_seen_at": db_image.last_seen_at.isoformat() if db_image.last_seen_at else None,
                            "description": db_image.description
                        }

            except Exception as e:
                logger.error(f"Erreur lors de la synchronisation DB: {e}")

        return images


    @chatbot_function(
        name="get_inactive_images_from_db",
        description="Récupère toutes les images marquées comme inactives dans la base de données",
        parameters_schema={
            "days_since_last_seen": {
                "type": "int",
                "required": False,
                "description": "Filtrer les images non vues depuis X jours"
            },
            "include_details": {
                "type": "bool",
                "required": False,
                "description": "Inclure les détails complets depuis la DB"
            }
        },
        examples=[
            "Affiche-moi toutes les images inactives",
            "Quelles images n'ont pas été vues depuis 30 jours ?",
            "Liste les images supprimées du registry mais encore en base"
        ]
    )
    def get_inactive_images_from_db(self, days_since_last_seen: Optional[int] = None,
                                    include_details: bool = True) -> List[Dict]:
        """Récupère les images inactives depuis la base de données"""
        try:
            if days_since_last_seen:
                db_images = self.image_repository.get_inactive_images(limit=1000)
            else:
                db_images = self.image_repository.get_inactive_images(limit=1000)

            result = []
            for db_image in db_images:
                image_info = {
                    "name": db_image.name,
                    "is_active": db_image.is_active,
                    "is_deployed": db_image.is_deployed,
                    "last_seen_at": db_image.last_seen_at.isoformat() if db_image.last_seen_at else None,
                    "first_detected_at": db_image.first_detected_at.isoformat() if db_image.first_detected_at else None,
                    "days_since_last_seen": (
                                datetime.utcnow() - db_image.last_seen_at).days if db_image.last_seen_at else None
                }

                if include_details:
                    image_info.update({
                        "id": db_image.id,
                        "description": db_image.description,
                        "total_tags": db_image.total_tags,
                        "total_size_mb": db_image.total_size_mb,
                        "deployed_tags_count": db_image.deployed_tags_count,
                        "architecture": db_image.architecture,
                        "os": db_image.os,
                        "created_at": db_image.created_at.isoformat() if db_image.created_at else None,
                        "updated_at": db_image.updated_at.isoformat() if db_image.updated_at else None
                    })

                result.append(image_info)

            return result

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images inactives: {e}")
            return []

    @chatbot_function(
        name="get_database_statistics",
        description="Récupère des statistiques complètes sur les images dans la base de données",
        parameters_schema={},
        examples=[
            "Affiche-moi les statistiques des images",
            "Combien d'images sont actives vs inactives ?",
            "Donne-moi un résumé de l'état des images"
        ]
    )
    def get_database_statistics(self) -> Dict[str, Any]:
        """Récupère des statistiques depuis la base de données"""
        try:
            stats = self.image_repository.get_statistics()

            # Ajouter des informations supplémentaires
            stats["last_sync"] = datetime.utcnow().isoformat()
            stats["sync_recommendation"] = "Exécutez get_images_with_deployment_status pour synchroniser" if stats[
                                                                                                                 "total_images"] == 0 else "Base de données à jour"

            return stats

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des statistiques: {e}")
            return {"error": str(e)}

    @chatbot_function(
        name="cleanup_inactive_images",
        description="⚠️ ATTENTION: Supprime les images inactives de la base de données selon des critères d'âge",
        parameters_schema={
            "older_than_days": {
                "type": "int",
                "required": False,
                "description": "Supprimer les images inactives non vues depuis X jours (défaut: 90)"
            },
            "dry_run": {
                "type": "bool",
                "required": False,
                "description": "Mode simulation pour voir quelles images seraient supprimées"
            },
            "user_confirmed": {
                "type": "bool",
                "required": False,
                "description": "Confirmation explicite de l'utilisateur"
            }
        },
        examples=[
            "Nettoie les images inactives plus anciennes que 90 jours",
            "Fais un dry-run du nettoyage des images anciennes",
            "Supprime les images inactives depuis plus de 6 mois"
        ]
    )
    def cleanup_inactive_images(self, older_than_days: int = 90, dry_run: bool = True,
                                user_confirmed: bool = False) -> Dict[str, Any]:
        """Nettoie les images inactives de la base de données"""
        try:
            # Récupérer les images qui seraient supprimées
            images_to_cleanup = self.get_inactive_images_from_db(days_since_last_seen=older_than_days)

            if dry_run or not user_confirmed:
                return {
                    "dry_run": dry_run,
                    "user_confirmed": user_confirmed,
                    "images_to_delete": len(images_to_cleanup),
                    "preview": [
                        {
                            "name": img["name"],
                            "last_seen_days_ago": img["days_since_last_seen"],
                            "was_deployed": img["is_deployed"]
                        }
                        for img in images_to_cleanup[:10]  # Limite l'aperçu
                    ],
                    "cutoff_days": older_than_days,
                    "action_required": None if dry_run else f"Pour confirmer, dites: 'Oui, je confirme le nettoyage de {len(images_to_cleanup)} images inactives'"
                }

            # Exécution réelle
            result = self.image_repository.delete_inactive_images(older_than_days)

            return {
                "dry_run": False,
                "user_confirmed": True,
                "cleanup_completed": result["success"],
                "deleted_count": result["deleted_count"],
                "deleted_images": result.get("deleted_images", []),
                "cutoff_date": result.get("cutoff_date"),
                "error": result.get("error") if not result["success"] else None
            }

        except Exception as e:
            logger.error(f"Erreur lors du nettoyage: {e}")
            return {
                "dry_run": dry_run,
                "error": str(e),
                "cleanup_completed": False
            }

    @chatbot_function(
        name="update_image_description",
        description="Met à jour la description d'une image dans la base de données",
        parameters_schema={
            "image_name": {
                "type": "str",
                "required": True,
                "description": "Nom de l'image à modifier"
            },
            "description": {
                "type": "str",
                "required": True,
                "description": "Nouvelle description de l'image"
            }
        },
        examples=[
            "Mets à jour la description de l'image nginx/web",
            "Ajoute une description à l'image myapp/backend",
            "Change la description de l'image app/frontend"
        ]
    )
    def update_image_description(self, image_name: str, description: str) -> Dict[str, Any]:
        """Met à jour la description d'une image"""
        try:
            db_image = self.image_repository.get_by_name(image_name)

            if not db_image:
                return {
                    "success": False,
                    "message": f"❌ Image '{image_name}' non trouvée dans la base de données",
                    "suggestion": "Exécutez d'abord get_images_with_deployment_status pour synchroniser"
                }

            # Mettre à jour la description
            updated_image = self.image_repository.update(db_image.id, {"description": description})

            if updated_image:
                return {
                    "success": True,
                    "message": f"✅ Description mise à jour pour '{image_name}'",
                    "image_name": image_name,
                    "new_description": description,
                    "updated_at": updated_image.updated_at.isoformat()
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Échec de la mise à jour de la description pour '{image_name}'"
                }

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la description: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @chatbot_function(
        name="get_filtered_images",
        description="Récupère les images filtrées selon différents critères (déployées, non-déployées, anciennes, volumineuses, actives, inactives, etc.)",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "description": "Namespace Kubernetes spécifique"
            },
            "filter_criteria": {
                "type": "str",
                "required": False,
                "description": "Critère de filtrage: 'all', 'deployed', 'not_deployed', 'older_than', 'modified_before', 'larger_than', 'unused_tags', 'active', 'inactive'"
            },
            "days_old": {
                "type": "int",
                "required": False,
                "description": "Nombre de jours pour les filtres 'older_than' et 'modified_before'"
            },
            "size_mb": {
                "type": "int",
                "required": False,
                "description": "Taille en MB pour le filtre 'larger_than'"
            },
            "include_details": {
                "type": "bool",
                "required": False,
                "description": "Inclure les détails complets des tags (taille, dates, etc.)"
            },
            "use_database": {
                "type": "bool",
                "required": False,
                "description": "Utiliser les données de la base de données pour les filtres active/inactive"
            }
        },
        examples=[
            "Trouve-moi les images non déployées",
            "Affiche les images plus anciennes que 30 jours",
            "Quelles images font plus de 500MB ?",
            "Liste les images inactives depuis la base de données",
            "Montre-moi les images actives avec leurs descriptions"
        ]
    )
    def get_filtered_images(self,
                            namespace: Optional[str] = None,
                            filter_criteria: str = "all",
                            days_old: int = 30,
                            size_mb: int = 100,
                            include_details: bool = False,
                            use_database: bool = False) -> List[Dict]:
        """Récupère les images filtrées selon les critères"""

        try:
            if isinstance(filter_criteria, ImageFilterCriteria):
                criteria = filter_criteria
            else:
                criteria = ImageFilterCriteria(filter_criteria.lower())
        except ValueError:
            criteria = ImageFilterCriteria.ALL

        if criteria in [ImageFilterCriteria.ACTIVE, ImageFilterCriteria.INACTIVE]:
            if criteria == ImageFilterCriteria.ACTIVE:
                db_images = self.image_repository.get_active_images(limit=1000)
            else:
                db_images = self.image_repository.get_inactive_images(limit=1000)

            # Convertir les images DB en format de réponse
            result = []
            for db_image in db_images:
                image_data = {
                    "name": db_image.name,
                    "tags": [],  # Les tags ne sont pas stockés en DB
                    "tag_count": db_image.total_tags,
                    "is_deployed": db_image.is_deployed,
                    "deployed_tags": [],
                    "deployed_tags_count": db_image.deployed_tags_count,
                    "total_size": db_image.total_size_bytes,
                    "total_size_mb": db_image.total_size_mb,
                    "db_info": {
                        "id": db_image.id,
                        "is_active": db_image.is_active,
                        "description": db_image.description,
                        "first_detected_at": db_image.first_detected_at.isoformat() if db_image.first_detected_at else None,
                        "last_seen_at": db_image.last_seen_at.isoformat() if db_image.last_seen_at else None,
                        "days_since_last_seen": (
                                    datetime.utcnow() - db_image.last_seen_at).days if db_image.last_seen_at else None
                    }
                }
                result.append(image_data)

            return result

        all_images = self.get_images_with_deployment_status(namespace, sync_database=use_database)
        filtered_images = []

        for image in all_images:
            # Appliquer les filtres
            if self._matches_filter(image, criteria, days_old, size_mb):
                # Si include_details est False, on peut retirer les detailed_tags
                if not include_details and "detailed_tags" in image:
                    image_copy = image.copy()
                    del image_copy["detailed_tags"]
                    filtered_images.append(image_copy)
                else:
                    filtered_images.append(image)

        return filtered_images

    @chatbot_function(
        name="get_image_details",
        description="Récupère les détails complets d'un tag d'image spécifique (taille, dates de création/modification, layers, etc.) avec informations de la base de données",
        parameters_schema={
            "image_name": {
                "type": "str",
                "required": True,
                "description": "Nom de l'image (ex: myapp/backend)"
            },
            "tag": {
                "type": "str",
                "required": True,
                "description": "Tag de l'image (ex: v1.0.0, latest)"
            }
        },
        examples=[
            "Affiche les détails de l'image myapp/backend:v1.0.0",
            "Quelle est la taille de l'image nginx:latest ?",
            "Montre-moi les informations de l'image app:production"
        ]
    )
    def get_image_details(self, image_name: str, tag: str) -> Dict:
        """Récupère les détails d'un tag d'image spécifique"""
        details = self.registry_client.get_detailed_image_info(image_name, tag)

        # Ajouter le statut de déploiement
        images_with_status = self.get_images_with_deployment_status()
        target_image = next((img for img in images_with_status if img["name"] == image_name), None)

        if target_image:
            details["is_deployed"] = tag in target_image["deployed_tags"]
            details["deployment_info"] = {
                "image_deployed": target_image["is_deployed"],
                "deployed_tags": target_image["deployed_tags"],
                "this_tag_deployed": tag in target_image["deployed_tags"]
            }
        else:
            details["is_deployed"] = False
            details["deployment_info"] = {
                "image_deployed": False,
                "deployed_tags": [],
                "this_tag_deployed": False
            }

        # Ajouter les informations de la base de données
        db_image = self.image_repository.get_by_name(image_name)
        if db_image:
            details["database_info"] = {
                "id": db_image.id,
                "is_active": db_image.is_active,
                "description": db_image.description,
                "first_detected_at": db_image.first_detected_at.isoformat() if db_image.first_detected_at else None,
                "last_seen_at": db_image.last_seen_at.isoformat() if db_image.last_seen_at else None,
                "days_since_last_seen": (
                            datetime.utcnow() - db_image.last_seen_at).days if db_image.last_seen_at else None,
                "total_tags_count": db_image.total_tags,
                "deployed_tags_count": db_image.deployed_tags_count
            }
        else:
            details["database_info"] = {
                "in_database": False,
                "note": "Image non synchronisée avec la base de données"
            }

        return details

    @chatbot_function(
        name="delete_entire_image",
        description="⚠️ ATTENTION: Supprime une image complète avec tous ses tags du registry ET met à jour la base de données. NÉCESSITE UNE CONFIRMATION de l'utilisateur avant exécution.",
        parameters_schema={
            "image_name": {
                "type": "str",
                "required": True,
                "description": "Nom complet de l'image à supprimer (ex: myapp/backend)"
            },
            "user_confirmed": {
                "type": "bool",
                "required": False,
                "description": "Confirmation explicite de l'utilisateur pour procéder à la suppression"
            }
        },
        examples=[
            "Supprime complètement l'image myapp/old-service",
            "Je veux supprimer l'image nginx/test avec tous ses tags",
            "Efface définitivement l'image app/deprecated"
        ]
    )
    def delete_entire_image(self, image_name: str, user_confirmed: bool = False) -> Dict:
        """Supprime une image complète (tous ses tags) avec vérification et mise à jour de la DB"""

        # Vérifier d'abord si l'image existe
        try:
            tags = self.registry_client.get_image_tags(image_name)
            if not tags:
                return {
                    "success": False,
                    "message": f"❌ Image '{image_name}' non trouvée ou sans tags",
                    "action_required": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"❌ Erreur lors de la vérification de l'image: {str(e)}",
                "action_required": None
            }

        images_with_status = self.get_images_with_deployment_status()
        target_image = next((img for img in images_with_status if img["name"] == image_name), None)

        if target_image and target_image["is_deployed"]:
            return {
                "success": False,
                "message": f"❌ Impossible de supprimer l'image '{image_name}': elle a des tags déployés",
                "deployed_tags": target_image['deployed_tags'],
                "total_tags": len(tags),
                "action_required": "Vous devez d'abord déployer d'autres versions ou arrêter les déploiements utilisant cette image"
            }

        # Si pas de confirmation utilisateur, demander confirmation
        if not user_confirmed:
            return {
                "success": False,
                "message": f"⚠️ CONFIRMATION REQUISE",
                "confirmation_details": {
                    "image_name": image_name,
                    "total_tags": len(tags),
                    "tags_to_delete": tags,
                    "is_deployed": False,
                    "warning": "Cette action supprimera DÉFINITIVEMENT l'image et tous ses tags du registry"
                },
                "action_required": "Veuillez confirmer explicitement que vous souhaitez supprimer cette image avec tous ses tags",
                "confirmation_message": f"Pour confirmer, dites: 'Oui, je confirme la suppression de l'image {image_name}'"
            }

        # Procéder à la suppression avec confirmation
        try:
            result = self.registry_client.delete_entire_image(image_name, tags)

            max_retries = 3
            verification_passed = False

            for attempt in range(max_retries):
                time.sleep(1)
                remaining_tags = self.registry_client.get_image_tags(image_name)

                if not remaining_tags:
                    verification_passed = True
                    logger.info(f"Vérification réussie: Image {image_name} supprimée")
                    break
                else:
                    logger.warning(f"Tentative {attempt + 1}/{max_retries}: {len(remaining_tags)} tags restants")

            # Mettre à jour la bdd
            db_update_success = False
            try:
                db_image = self.image_repository.get_by_name(image_name)
                if db_image:
                    # Marquer comme inactive plutôt que supprimer pour garder l'historique
                    self.image_repository.update(db_image.id, {
                        "is_active": False,
                        "last_seen_at": datetime.utcnow()
                    })
                    db_update_success = True
                    logger.info(f"Image {image_name} marquée comme inactive dans la DB")
            except Exception as db_error:
                logger.warning(f"Erreur lors de la mise à jour DB pour {image_name}: {db_error}")

            if verification_passed:
                return {
                    "success": True,
                    "message": f"✅ Image '{image_name}' supprimée avec succès",
                    "deleted_tags": tags,
                    "total_tags_deleted": len(tags),
                    "verification_passed": True,
                    "database_updated": db_update_success
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Échec de la suppression de l'image '{image_name}'",
                    "error": "Tags encore présents après suppression",
                    "remaining_tags": self.registry_client.get_image_tags(image_name)
                }

        except Exception as e:
            logger.error(f"Erreur lors de la suppression: {e}")
            return {
                "success": False,
                "message": f"❌ Erreur lors de la suppression: {str(e)}",
                "error": str(e)
            }

    @chatbot_function(
        name="purge_images",
        description="⚠️ ATTENTION: Purge (supprime) plusieurs images selon des critères spécifiés et met à jour la base de données. NÉCESSITE UNE CONFIRMATION de l'utilisateur avant exécution réelle.",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "description": "Namespace Kubernetes spécifique"
            },
            "filter_criteria": {
                "type": "str",
                "required": False,
                "description": "Critère de filtrage: 'not_deployed', 'older_than', 'larger_than', 'unused_tags', 'inactive'"
            },
            "days_old": {
                "type": "int",
                "required": False,
                "description": "Nombre de jours pour les filtres temporels (défaut: 30)"
            },
            "size_mb": {
                "type": "int",
                "required": False,
                "description": "Taille en MB pour le filtre de taille (défaut: 100)"
            },
            "dry_run": {
                "type": "bool",
                "required": False,
                "description": "Mode simulation (true) ou exécution réelle (false)"
            },
            "user_confirmed": {
                "type": "bool",
                "required": False,
                "description": "Confirmation explicite de l'utilisateur pour l'exécution réelle"
            }
        },
        examples=[
            "Purge les images non déployées plus anciennes que 60 jours",
            "Supprime toutes les images non utilisées",
            "Nettoie les images de plus de 1GB qui ne sont pas déployées",
            "Fais un dry-run pour voir quelles images seraient supprimées"
        ]
    )
    def purge_images(self,
                     namespace: Optional[str] = None,
                     filter_criteria: str = "not_deployed",
                     days_old: int = 30,
                     size_mb: int = 100,
                     dry_run: bool = True,
                     user_confirmed: bool = False) -> Dict:
        """Purge les images selon les critères spécifiés avec confirmation obligatoire et mise à jour DB"""

        try:
            if isinstance(filter_criteria, ImageFilterCriteria):
                criteria = filter_criteria
            else:
                criteria = ImageFilterCriteria(filter_criteria.lower())
        except ValueError:
            criteria = ImageFilterCriteria.NOT_DEPLOYED

        # Récupérer les images à purger
        images_to_purge = self.get_filtered_images(
            namespace=namespace,
            filter_criteria=filter_criteria,
            days_old=days_old,
            size_mb=size_mb,
            include_details=True
        )

        images_to_delete = []
        tags_to_delete = []
        estimated_space = 0
        errors = []

        # Traitement des images pour identifier ce qui sera supprimé
        for image in images_to_purge:
            # Déterminer les tags à supprimer
            non_deployed_tags = [tag for tag in image["tags"] if tag not in image["deployed_tags"]]

            if non_deployed_tags:
                # Calculer la taille estimée pour cette image
                image_size = 0
                if "detailed_tags" in image:
                    for detailed_tag in image["detailed_tags"]:
                        if detailed_tag["tag"] in non_deployed_tags:
                            image_size += detailed_tag.get("size", 0)

                # Ajouter à la liste des images à supprimer
                image_info = {
                    "name": image["name"],
                    "total_tags": len(image["tags"]),
                    "deployed_tags": image["deployed_tags"],
                    "tags_to_delete": non_deployed_tags,
                    "is_deployed": image["is_deployed"],
                    "estimated_size_mb": round(image_size / (1024 * 1024), 2) if image_size > 0 else 0
                }
                images_to_delete.append(image_info)

                # Ajouter chaque tag à la liste globale
                for tag in non_deployed_tags:
                    tag_info = {
                        "image_name": image["name"],
                        "tag": tag
                    }
                    tags_to_delete.append(tag_info)

                estimated_space += image_size

        # Si c'est un dry_run ou pas de confirmation pour une exécution réelle
        if dry_run or not user_confirmed:
            return {
                # Champs obligatoires pour le schéma PurgeResultResponse
                "dry_run": dry_run,
                "user_confirmed": user_confirmed,
                "total_images_evaluated": len(images_to_purge),
                "images_to_delete": images_to_delete,
                "tags_to_delete": tags_to_delete,
                "estimated_space_freed": round(estimated_space / (1024 * 1024), 2),
                "errors": errors,

                # Champs optionnels pour le preview
                "preview": {
                    "total_images_to_process": len(images_to_purge),
                    "total_tags_to_delete": len(tags_to_delete),
                    "estimated_space_freed_mb": round(estimated_space / (1024 * 1024), 2),
                    "filter_criteria": filter_criteria,
                    "namespace": namespace,
                    "days_old": days_old,
                    "size_mb_threshold": size_mb
                },
                "images_preview": images_to_delete[:10],  # Limiter l'aperçu aux 10 premiers
                "action_required": None if dry_run else "Pour exécuter réellement cette purge, confirmez explicitement votre intention",
                "confirmation_message": None if dry_run else f"Pour confirmer, dites: 'Oui, je confirme la purge de {len(tags_to_delete)} tags selon les critères {filter_criteria}'"
            }

        # Exécution réelle avec confirmation
        actual_deleted_images = []
        actual_deleted_tags = []
        actual_space_freed = 0
        execution_errors = []
        success_count = 0

        # Traitement de chaque image pour suppression réelle
        for image_info in images_to_delete:
            image_name = image_info["name"]
            tags_to_remove = image_info["tags_to_delete"]

            image_result = {
                "name": image_name,
                "deleted_tags": [],
                "errors": []
            }

            # Suppression de chaque tag non déployé
            for tag in tags_to_remove:
                try:
                    success = self.registry_client.delete_image_tag(image_name, tag)
                    if success:
                        actual_deleted_tags.append({
                            "image_name": image_name,
                            "tag": tag,
                            "deleted_at": datetime.now().isoformat()
                        })
                        image_result["deleted_tags"].append(tag)
                        success_count += 1

                        # Calculer l'espace réellement libéré
                        # Récupérer la taille depuis les détails originaux
                        original_image = next((img for img in images_to_purge if img["name"] == image_name), None)
                        if original_image and "detailed_tags" in original_image:
                            for detailed_tag in original_image["detailed_tags"]:
                                if detailed_tag["tag"] == tag:
                                    actual_space_freed += detailed_tag.get("size", 0)
                                    break

                        logger.info(f"✅ Tag supprimé: {image_name}:{tag}")
                    else:
                        error_msg = f"Échec suppression {image_name}:{tag}"
                        execution_errors.append(error_msg)
                        image_result["errors"].append(error_msg)
                except Exception as e:
                    error_msg = f"Erreur {image_name}:{tag}: {str(e)}"
                    execution_errors.append(error_msg)
                    image_result["errors"].append(error_msg)
                    logger.error(error_msg)

            # Ajouter le résultat de l'image si des tags ont été supprimés
            if image_result["deleted_tags"]:
                actual_deleted_images.append(image_result)

            # Vérifier si l'image entière a été supprimée et mettre à jour la DB
            if len(image_result["deleted_tags"]) == len(tags_to_remove):
                # Vérifier s'il reste des tags déployés
                remaining_deployed = image_info.get("deployed_tags", [])
                if not remaining_deployed:
                    # Image complètement supprimée, mettre à jour la base de données
                    try:
                        db_image = self.image_repository.get_by_name(image_name)
                        if db_image:
                            self.image_repository.update(db_image.id, {
                                "is_active": False,
                                "last_seen_at": datetime.utcnow()
                            })
                            logger.info(f"Image {image_name} marquée comme inactive dans la DB")
                    except Exception as db_error:
                        logger.warning(f"Erreur DB pour {image_name}: {db_error}")
                        execution_errors.append(f"Erreur DB pour {image_name}: {str(db_error)}")

        # Retourner le résultat final conforme au schéma
        return {
            # Champs obligatoires
            "dry_run": False,
            "user_confirmed": True,
            "total_images_evaluated": len(images_to_purge),
            "images_to_delete": actual_deleted_images,
            "tags_to_delete": actual_deleted_tags,
            "estimated_space_freed": round(actual_space_freed / (1024 * 1024), 2),
            "errors": execution_errors,

            # Informations supplémentaires pour compatibilité
            "execution_summary": {
                "execution_started": datetime.now().isoformat(),
                "execution_completed": datetime.now().isoformat(),
                "success_count": success_count,
                "error_count": len(execution_errors),
                "images_fully_deleted": len([img for img in actual_deleted_images if not any(
                    original["deployed_tags"] for original in images_to_delete if original["name"] == img["name"])]),
                "total_tags_deleted": len(actual_deleted_tags),
                "space_freed_mb": round(actual_space_freed / (1024 * 1024), 2),
                "message": f"✅ Purge terminée: {len(actual_deleted_tags)} tags supprimés" if len(
                    execution_errors) == 0 else f"⚠️ Purge terminée avec {len(execution_errors)} erreurs"
            }
        }

    # Méthodes utilitaires (non exposées au chatbot)
    def get_catalog(self) -> List[str]:
        """Récupère le catalogue des images"""
        return self.registry_client.get_catalog()

    def delete_image_tag(self, image_name: str, tag: str) -> bool:
        """Supprime un tag d'image spécifique"""
        return self.registry_client.delete_image_tag(image_name, tag)

    def verify_image_deletion(self, image_name: str) -> Dict:
        """Vérifie qu'une image a bien été supprimée"""
        try:
            tags = self.registry_client.get_image_tags(image_name)
            catalog = self.registry_client.get_catalog()
            in_catalog = image_name in catalog

            images_with_status = self.get_images_with_deployment_status()
            deployed_image = next((img for img in images_with_status if img["name"] == image_name), None)

            effectively_deleted = not tags and not deployed_image

            return {
                "image_name": image_name,
                "effectively_deleted": effectively_deleted,
                "in_catalog": in_catalog,
                "tags_count": len(tags),
                "tags": tags,
                "is_deployed": deployed_image is not None,
                "deployed_tags": deployed_image["deployed_tags"] if deployed_image else [],
                "note": "Image considered deleted if no tags remain, even if still in catalog"
            }
        except Exception as e:
            logger.error(f"Erreur lors de la vérification de suppression: {e}")
            return {
                "image_name": image_name,
                "effectively_deleted": False,
                "error": str(e)
            }

    def _matches_filter(self, image: Dict, criteria: ImageFilterCriteria,
                        days_old: int, size_mb: int) -> bool:
        """Vérifie si une image correspond aux critères de filtrage"""

        if criteria == ImageFilterCriteria.ALL:
            return True

        elif criteria == ImageFilterCriteria.DEPLOYED:
            return image["is_deployed"]

        elif criteria == ImageFilterCriteria.NOT_DEPLOYED:
            return not image["is_deployed"]

        elif criteria == ImageFilterCriteria.UNUSED_TAGS:
            return len(image["tags"]) > len(image["deployed_tags"])

        elif criteria == ImageFilterCriteria.ACTIVE:
            # Vérifier le statut depuis la DB si disponible
            db_info = image.get("db_info")
            return db_info["is_active"] if db_info else True

        elif criteria == ImageFilterCriteria.INACTIVE:
            # Vérifier le statut depuis la DB si disponible
            db_info = image.get("db_info")
            return not db_info["is_active"] if db_info else False

        elif criteria == ImageFilterCriteria.LARGER_THAN:
            size_bytes = size_mb * 1024 * 1024
            if "detailed_tags" in image:
                for detailed_tag in image["detailed_tags"]:
                    if detailed_tag.get("size", 0) > size_bytes:
                        return True
            return False

        elif criteria == ImageFilterCriteria.OLDER_THAN:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            if "detailed_tags" in image:
                for detailed_tag in image["detailed_tags"]:
                    created_date = detailed_tag.get("created")
                    if created_date:
                        try:
                            tag_date = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                            if tag_date < cutoff_date:
                                return True
                        except:
                            continue
            return False

        elif criteria == ImageFilterCriteria.MODIFIED_BEFORE:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            if "detailed_tags" in image:
                for detailed_tag in image["detailed_tags"]:
                    last_modified = detailed_tag.get("last_modified")
                    if last_modified:
                        try:
                            modified_date = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                            if modified_date < cutoff_date:
                                return True
                        except:
                            continue
            return False

        return False