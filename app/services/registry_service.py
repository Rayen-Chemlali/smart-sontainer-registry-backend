from typing import List, Dict, Optional, Set
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
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


class RegistryService:
    def __init__(self, registry_client: RegistryClient, k8s_client: K8sClient):
        self.registry_client = registry_client
        self.k8s_client = k8s_client

    @chatbot_function(
        name="get_images_with_deployment_status",
        description="Récupère toutes les images du registry avec leur statut de déploiement Kubernetes",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "description": "Namespace Kubernetes spécifique à analyser (optionnel)"
            }
        },
        examples=[
            "Affiche-moi toutes les images avec leur statut de déploiement",
            "Quelles images sont déployées dans le namespace production ?",
            "Liste les images du registry avec leurs tags déployés"
        ]
    )
    def get_images_with_deployment_status(self, namespace: Optional[str] = None) -> List[Dict]:
        """Récupère toutes les images avec leur statut de déploiement"""
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

            images.append({
                "name": image_name,
                "tags": tags,
                "tag_count": len(tags),
                "is_deployed": is_deployed,
                "deployed_tags": deployed_tags,
                "deployed_tags_count": len(deployed_tags)
            })

        return images

    @chatbot_function(
        name="get_filtered_images",
        description="Récupère les images filtrées selon différents critères (déployées, non-déployées, anciennes, volumineuses, etc.)",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "description": "Namespace Kubernetes spécifique"
            },
            "filter_criteria": {
                "type": "str",
                "required": False,
                "description": "Critère de filtrage: 'all', 'deployed', 'not_deployed', 'older_than', 'modified_before', 'larger_than', 'unused_tags'"
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
                "description": "Inclure les détails complets des tags (taille, dates, etc.)lower"
            }
        },
        examples=[
            "Trouve-moi les images non déployées",
            "Affiche les images plus anciennes que 30 jours",
            "Quelles images font plus de 500MB ?",
            "Liste les images avec des tags inutilisés"
        ]
    )
    def get_filtered_images(self,
                            namespace: Optional[str] = None,
                            filter_criteria: str = "all",
                            days_old: int = 30,
                            size_mb: int = 100,
                            include_details: bool = False) -> List[Dict]:
        """Récupère les images filtrées selon les critères"""

        # Handle both string and enum inputs for filter_criteria
        try:
            if isinstance(filter_criteria, ImageFilterCriteria):
                criteria = filter_criteria
            else:
                criteria = ImageFilterCriteria(filter_criteria.lower())
        except ValueError:
            criteria = ImageFilterCriteria.ALL

        # Récupérer toutes les images avec statut de déploiement
        all_images = self.get_images_with_deployment_status(namespace)
        filtered_images = []

        for image in all_images:
            image_name = image["name"]

            # Appliquer d'abord les filtres simples (sans nécessiter de détails)
            if self._matches_filter(image, criteria, days_old, size_mb):
                # Ajouter les détails seulement pour les images qui passent le filtre
                if include_details:
                    detailed_tags = []
                    for tag in image["tags"]:
                        try:
                            tag_info = self.registry_client.get_detailed_image_info(image_name, tag)
                            detailed_tags.append({
                                "tag": tag,
                                "size": tag_info.get("size", 0),
                                "created": tag_info.get("created"),
                                "last_modified": tag_info.get("last_modified"),
                                "is_deployed": tag in image["deployed_tags"]
                            })
                        except Exception as e:
                            logger.warning(f"Impossible de récupérer les détails pour {image_name}:{tag}: {e}")
                            # Ajouter des détails par défaut en cas d'erreur
                            detailed_tags.append({
                                "tag": tag,
                                "size": 0,
                                "created": None,
                                "last_modified": None,
                                "is_deployed": tag in image["deployed_tags"],
                                "error": str(e)
                            })
                    image["detailed_tags"] = detailed_tags

                filtered_images.append(image)

        return filtered_images

    @chatbot_function(
        name="get_image_details",
        description="Récupère les détails complets d'un tag d'image spécifique (taille, dates de création/modification, layers, etc.)",
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

        return details

    @chatbot_function(
        name="delete_entire_image",
        description="⚠️ ATTENTION: Supprime une image complète avec tous ses tags du registry. NÉCESSITE UNE CONFIRMATION de l'utilisateur avant exécution.",
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
        """Supprime une image complète (tous ses tags) avec vérification et confirmation"""

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

        # Vérifier si l'image est déployée
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

            # Vérification améliorée
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

            if verification_passed:
                return {
                    "success": True,
                    "message": f"✅ Image '{image_name}' supprimée avec succès",
                    "deleted_tags": tags,
                    "total_tags_deleted": len(tags),
                    "verification_passed": True
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
        description="⚠️ ATTENTION: Purge (supprime) plusieurs images selon des critères spécifiés. NÉCESSITE UNE CONFIRMATION de l'utilisateur avant exécution réelle.",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "description": "Namespace Kubernetes spécifique"
            },
            "filter_criteria": {
                "type": "str",
                "required": False,
                "description": "Critère de filtrage: 'not_deployed', 'older_than', 'larger_than', 'unused_tags'"
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
        """Purge les images selon les critères spécifiés avec confirmation obligatoire"""

        # Handle both string and enum inputs for filter_criteria
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

        # Calcul de l'espace estimé à libérer
        estimated_space = 0
        tags_to_delete_count = 0

        for image in images_to_purge:
            # Compter seulement les tags non déployés
            non_deployed_tags = [tag for tag in image["tags"] if tag not in image["deployed_tags"]]
            tags_to_delete_count += len(non_deployed_tags)

            if "detailed_tags" in image:
                for detailed_tag in image["detailed_tags"]:
                    if not detailed_tag["is_deployed"]:
                        estimated_space += detailed_tag.get("size", 0)

        # Si c'est un dry_run ou pas de confirmation pour une exécution réelle
        if dry_run or not user_confirmed:
            return {
                "dry_run": dry_run,
                "user_confirmed": user_confirmed,
                "preview": {
                    "total_images_to_process": len(images_to_purge),
                    "total_tags_to_delete": tags_to_delete_count,
                    "estimated_space_freed_mb": round(estimated_space / (1024 * 1024), 2),
                    "filter_criteria": filter_criteria,
                    "namespace": namespace,
                    "days_old": days_old,
                    "size_mb_threshold": size_mb
                },
                "images_preview": [
                    {
                        "name": img["name"],
                        "total_tags": len(img["tags"]),
                        "deployed_tags": img["deployed_tags"],
                        "tags_to_delete": [tag for tag in img["tags"] if tag not in img["deployed_tags"]],
                        "is_deployed": img["is_deployed"]
                    }
                    for img in images_to_purge[:10]  # Limiter l'aperçu aux 10 premiers
                ],
                "action_required": None if dry_run else "Pour exécuter réellement cette purge, confirmez explicitement votre intention",
                "confirmation_message": None if dry_run else f"Pour confirmer, dites: 'Oui, je confirme la purge de {tags_to_delete_count} tags selon les critères {filter_criteria}'"
            }

        # Exécution réelle avec confirmation
        purge_results = {
            "dry_run": False,
            "user_confirmed": True,
            "execution_started": datetime.now().isoformat(),
            "total_images_evaluated": len(images_to_purge),
            "images_processed": [],
            "tags_deleted": [],
            "images_fully_deleted": [],
            "estimated_space_freed": 0,
            "errors": [],
            "success_count": 0,
            "error_count": 0
        }

        # Traitement de chaque image
        for image in images_to_purge:
            image_name = image["name"]
            tags_to_delete = [tag for tag in image["tags"] if tag not in image["deployed_tags"]]

            if not tags_to_delete:
                continue

            image_result = {
                "name": image_name,
                "total_tags": len(image["tags"]),
                "tags_to_delete": tags_to_delete,
                "deployed_tags": image["deployed_tags"],
                "deleted_tags": [],
                "errors": []
            }

            # Suppression de chaque tag non déployé
            for tag in tags_to_delete:
                tag_info = {
                    "image": image_name,
                    "tag": tag,
                    "size": 0,
                    "deleted_at": datetime.now().isoformat()
                }

                # Récupérer la taille du tag
                if "detailed_tags" in image:
                    for detailed_tag in image["detailed_tags"]:
                        if detailed_tag["tag"] == tag:
                            tag_info["size"] = detailed_tag.get("size", 0)
                            break

                try:
                    success = self.registry_client.delete_image_tag(image_name, tag)
                    if success:
                        purge_results["tags_deleted"].append(tag_info)
                        image_result["deleted_tags"].append(tag)
                        purge_results["success_count"] += 1
                        purge_results["estimated_space_freed"] += tag_info["size"]
                        logger.info(f"✅ Tag supprimé: {image_name}:{tag}")
                    else:
                        error_msg = f"❌ Échec suppression {image_name}:{tag}"
                        purge_results["errors"].append(error_msg)
                        image_result["errors"].append(error_msg)
                        purge_results["error_count"] += 1
                except Exception as e:
                    error_msg = f"❌ Erreur {image_name}:{tag}: {str(e)}"
                    purge_results["errors"].append(error_msg)
                    image_result["errors"].append(error_msg)
                    purge_results["error_count"] += 1
                    logger.error(error_msg)

            # Vérifier si l'image entière a été supprimée
            remaining_tags = [tag for tag in image["tags"] if tag in image["deployed_tags"]]
            if len(image_result["deleted_tags"]) == len(tags_to_delete) and not remaining_tags:
                purge_results["images_fully_deleted"].append(image_name)
                image_result["fully_deleted"] = True

            purge_results["images_processed"].append(image_result)

        # Résumé final
        purge_results["execution_completed"] = datetime.now().isoformat()
        purge_results["summary"] = {
            "success": purge_results["error_count"] == 0,
            "images_processed": len(purge_results["images_processed"]),
            "images_fully_deleted": len(purge_results["images_fully_deleted"]),
            "total_tags_deleted": len(purge_results["tags_deleted"]),
            "total_errors": purge_results["error_count"],
            "space_freed_mb": round(purge_results["estimated_space_freed"] / (1024 * 1024), 2),
            "message": f"✅ Purge terminée: {len(purge_results['tags_deleted'])} tags supprimés" if purge_results[
                                                                                                       "error_count"] == 0 else f"⚠️ Purge terminée avec {purge_results['error_count']} erreurs"
        }

        return purge_results

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

        elif criteria == ImageFilterCriteria.LARGER_THAN:
            size_bytes = size_mb * 1024 * 1024
            # Vérifier si on a les détails des tags ou récupérer la taille
            if "detailed_tags" in image:
                # Utiliser les détails déjà récupérés
                for detailed_tag in image["detailed_tags"]:
                    if detailed_tag.get("size", 0) > size_bytes:
                        return True
            else:
                # Récupérer la taille directement avec gestion d'erreur
                for tag in image["tags"]:
                    try:
                        tag_size = self.registry_client.get_image_size(image["name"], tag)
                        if tag_size > size_bytes:
                            return True
                    except Exception as e:
                        logger.warning(f"Impossible de récupérer la taille pour {image['name']}:{tag}: {e}")
                        # En cas d'erreur, on passe au tag suivant
                        continue
            return False

        elif criteria == ImageFilterCriteria.OLDER_THAN:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            for tag in image["tags"]:
                try:
                    created_date = self.registry_client.get_image_creation_date(image["name"], tag)
                    if created_date:
                        try:
                            tag_date = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                            if tag_date < cutoff_date:
                                return True
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Impossible de récupérer la date de création pour {image['name']}:{tag}: {e}")
                    continue
            return False

        elif criteria == ImageFilterCriteria.MODIFIED_BEFORE:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            for tag in image["tags"]:
                try:
                    tag_info = self.registry_client.get_detailed_image_info(image["name"], tag)
                    last_modified = tag_info.get("last_modified")
                    if last_modified:
                        try:
                            modified_date = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                            if modified_date < cutoff_date:
                                return True
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Impossible de récupérer les infos détaillées pour {image['name']}:{tag}: {e}")
                    continue
            return False

        return False

#add the trigger after every action