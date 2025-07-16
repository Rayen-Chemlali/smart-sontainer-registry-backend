from typing import List, Dict, Optional, Set
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
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
    LARGER_THAN = "larger_than"
    UNUSED_TAGS = "unused_tags"


class RegistryService:
    def __init__(self, registry_client: RegistryClient, k8s_client: K8sClient):
        self.registry_client = registry_client
        self.k8s_client = k8s_client

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

    def get_catalog(self) -> List[str]:
        """Récupère le catalogue des images"""
        return self.registry_client.get_catalog()

    def get_filtered_images(self,
                            namespace: Optional[str] = None,
                            filter_criteria: ImageFilterCriteria = ImageFilterCriteria.ALL,
                            days_old: int = 30,
                            size_mb: int = 100,
                            include_details: bool = False) -> List[Dict]:
        """Récupère les images filtrées selon les critères"""

        # Récupérer toutes les images avec statut de déploiement
        all_images = self.get_images_with_deployment_status(namespace)
        filtered_images = []

        for image in all_images:
            image_name = image["name"]

            # Ajouter les détails si demandé
            if include_details:
                detailed_tags = []
                for tag in image["tags"]:
                    tag_info = self.registry_client.get_detailed_image_info(image_name, tag)
                    detailed_tags.append({
                        "tag": tag,
                        "size": tag_info.get("size", 0),
                        "created": tag_info.get("created"),
                        "is_deployed": tag in image["deployed_tags"]
                    })
                image["detailed_tags"] = detailed_tags

            # Appliquer les filtres
            if self._matches_filter(image, filter_criteria, days_old, size_mb):
                filtered_images.append(image)

        return filtered_images

    def get_image_details(self, image_name: str, tag: str) -> Dict:
        """Récupère les détails d'un tag d'image spécifique"""
        return self.registry_client.get_detailed_image_info(image_name, tag)

    def delete_image_tag(self, image_name: str, tag: str) -> bool:
        """Supprime un tag d'image spécifique"""
        return self.registry_client.delete_image_tag(image_name, tag)

    def delete_entire_image(self, image_name: str) -> Dict:
        """Supprime une image complète (tous ses tags) avec vérification améliorée"""
        # Récupérer tous les tags de l'image
        tags = self.registry_client.get_image_tags(image_name)

        if not tags:
            return {
                "success": False,
                "message": f"Image {image_name} not found or has no tags",
                "deleted_tags": [],
                "errors": []
            }

        # Vérifier si l'image est déployée
        images_with_status = self.get_images_with_deployment_status()
        target_image = next((img for img in images_with_status if img["name"] == image_name), None)

        if target_image and target_image["is_deployed"]:
            return {
                "success": False,
                "message": f"Cannot delete image {image_name}: it has deployed tags {target_image['deployed_tags']}",
                "deleted_tags": [],
                "errors": [f"Image has deployed tags: {target_image['deployed_tags']}"]
            }

        # Supprimer tous les tags avec la méthode améliorée
        result = self.registry_client.delete_entire_image(image_name, tags)

        # Vérification améliorée - se concentrer sur les tags plutôt que sur le catalogue
        max_retries = 3
        verification_passed = False

        for attempt in range(max_retries):
            time.sleep(1)  # Attendre un peu

            # Vérifier si l'image a encore des tags (plus fiable que le catalogue)
            remaining_tags = self.registry_client.get_image_tags(image_name)

            if not remaining_tags:
                # Pas de tags = image effectivement supprimée
                verification_passed = True
                logger.info(f"Vérification réussie: Image {image_name} n'a plus de tags")
                break
            else:
                logger.warning(
                    f"Tentative {attempt + 1}/{max_retries}: Image {image_name} a encore {len(remaining_tags)} tags: {remaining_tags}")

        # Mise à jour du résultat basé sur la vérification
        if verification_passed:
            result["success"] = True
            result["message"] = f"Image {image_name} supprimée avec succès du registry"
            result["verification_passed"] = True

            # Note: L'image peut encore apparaître dans le catalogue temporairement
            # mais sans tags, elle est effectivement supprimée
            catalog = self.registry_client.get_catalog()
            if image_name in catalog:
                result[
                    "warning"] = f"Image {image_name} encore visible dans le catalogue mais sans tags (normal, sera nettoyée automatiquement)"
        else:
            result["success"] = False
            result["message"] = f"Échec de la suppression de l'image {image_name}: tags encore présents"
            result["verification_passed"] = False
            result["remaining_tags"] = self.registry_client.get_image_tags(image_name)

        return result

    def force_refresh_catalog(self) -> Dict:
        """Force le rafraîchissement du catalogue registry"""
        try:
            # Récupérer le catalogue à nouveau
            catalog = self.registry_client.get_catalog()

            # Déclencher le garbage collection si possible
            gc_result = self.registry_client.trigger_garbage_collection()

            return {
                "success": True,
                "catalog_size": len(catalog),
                "garbage_collection_triggered": gc_result,
                "message": "Catalogue rafraîchi"
            }
        except Exception as e:
            logger.error(f"Erreur lors du rafraîchissement du catalogue: {e}")
            return {
                "success": False,
                "message": f"Erreur: {str(e)}"
            }

    def verify_image_deletion(self, image_name: str) -> Dict:
        """Vérifie qu'une image a bien été supprimée - version améliorée"""
        try:
            # Vérifier les tags (critère principal)
            tags = self.registry_client.get_image_tags(image_name)

            # Vérifier dans le catalogue (informatif seulement)
            catalog = self.registry_client.get_catalog()
            in_catalog = image_name in catalog

            # Vérifier les images déployées
            images_with_status = self.get_images_with_deployment_status()
            deployed_image = next((img for img in images_with_status if img["name"] == image_name), None)

            # Une image est considérée comme supprimée si elle n'a plus de tags
            # même si elle apparaît encore dans le catalogue
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

        elif criteria == ImageFilterCriteria.OLDER_THAN:
            # Vérifier si au moins un tag est plus ancien que X jours
            cutoff_date = datetime.now() - timedelta(days=days_old)
            for tag in image["tags"]:
                created_date = self.registry_client.get_image_creation_date(image["name"], tag)
                if created_date:
                    try:
                        tag_date = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                        if tag_date < cutoff_date:
                            return True
                    except:
                        continue
            return False

        elif criteria == ImageFilterCriteria.LARGER_THAN:
            # Vérifier si au moins un tag est plus volumineux que X MB
            size_bytes = size_mb * 1024 * 1024
            for tag in image["tags"]:
                tag_size = self.registry_client.get_image_size(image["name"], tag)
                if tag_size > size_bytes:
                    return True
            return False

        return False

    def purge_images(self,
                     namespace: Optional[str] = None,
                     filter_criteria: ImageFilterCriteria = ImageFilterCriteria.NOT_DEPLOYED,
                     days_old: int = 30,
                     size_mb: int = 100,
                     dry_run: bool = True) -> Dict:
        """Purge les images selon les critères spécifiés"""

        # Récupérer les images à purger
        images_to_purge = self.get_filtered_images(
            namespace=namespace,
            filter_criteria=filter_criteria,
            days_old=days_old,
            size_mb=size_mb,
            include_details=True
        )

        purge_results = {
            "dry_run": dry_run,
            "total_images_evaluated": len(images_to_purge),
            "images_to_delete": [],
            "tags_to_delete": [],
            "estimated_space_freed": 0,
            "errors": []
        }

        for image in images_to_purge:
            image_name = image["name"]

            # Déterminer quels tags supprimer
            tags_to_delete = self._get_tags_to_delete(image, filter_criteria)

            for tag in tags_to_delete:
                tag_info = {
                    "image": image_name,
                    "tag": tag,
                    "size": 0,
                    "created": None,
                    "is_deployed": tag in image["deployed_tags"]
                }

                # Récupérer les détails du tag
                if "detailed_tags" in image:
                    for detailed_tag in image["detailed_tags"]:
                        if detailed_tag["tag"] == tag:
                            tag_info.update(detailed_tag)
                            break

                purge_results["tags_to_delete"].append(tag_info)
                purge_results["estimated_space_freed"] += tag_info["size"]

                # Effectuer la suppression si ce n'est pas un dry run
                if not dry_run:
                    success = self.registry_client.delete_image_tag(image_name, tag)
                    if not success:
                        purge_results["errors"].append(f"Échec de suppression de {image_name}:{tag}")

            if tags_to_delete:
                purge_results["images_to_delete"].append({
                    "name": image_name,
                    "tags_deleted": tags_to_delete,
                    "is_deployed": image["is_deployed"]
                })

        return purge_results

    def _get_tags_to_delete(self, image: Dict, criteria: ImageFilterCriteria) -> List[str]:
        """Détermine quels tags supprimer pour une image"""

        if criteria == ImageFilterCriteria.NOT_DEPLOYED:
            # Supprimer tous les tags non déployés
            return [tag for tag in image["tags"] if tag not in image["deployed_tags"]]

        elif criteria == ImageFilterCriteria.UNUSED_TAGS:
            # Supprimer les tags non utilisés (même logique que NOT_DEPLOYED)
            return [tag for tag in image["tags"] if tag not in image["deployed_tags"]]

        elif criteria in [ImageFilterCriteria.OLDER_THAN, ImageFilterCriteria.LARGER_THAN]:
            # Pour ces critères, on ne supprime que les tags non déployés qui correspondent
            tags_to_delete = []
            for tag in image["tags"]:
                if tag not in image["deployed_tags"]:  # Seulement les tags non déployés
                    tags_to_delete.append(tag)
            return tags_to_delete

        return []