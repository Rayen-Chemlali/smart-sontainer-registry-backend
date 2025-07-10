from typing import List, Dict, Optional, Set
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
from datetime import datetime, timedelta
from enum import Enum

class ImageFilterCriteria(Enum):
    """Critères de filtrage des images"""
    ALL = "all"
    DEPLOYED = "deployed"
    NOT_DEPLOYED = "not_deployed"
    OLDER_THAN = "older_than"
    LARGER_THAN = "larger_than"
    UNUSED_TAGS = "unused_tags"
import logging

logger = logging.getLogger(__name__)


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
