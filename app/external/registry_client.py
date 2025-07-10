import requests
import logging
from typing import List, Dict, Set, Tuple, Optional

logger = logging.getLogger(__name__)

class RegistryClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_catalog(self) -> List[str]:
        """Récupère le catalogue des images du registry"""
        try:
            response = requests.get(f"{self.base_url}/v2/_catalog", timeout=10)
            if response.status_code == 200:
                return response.json().get("repositories", [])
            else:
                logger.error(f"Erreur API registry: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du catalogue: {e}")
            return []

    def get_image_tags(self, image_name: str) -> List[str]:
        """Récupère les tags d'une image spécifique"""
        try:
            response = requests.get(f"{self.base_url}/v2/{image_name}/tags/list", timeout=10)
            if response.status_code == 200:
                return response.json().get("tags", [])
            else:
                return []
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des tags pour {image_name}: {e}")
            return []

    def normalize_image_name(self, image_full_name: str) -> str:
        """Normalise le nom d'image pour la comparaison"""
        if '/' in image_full_name:
            parts = image_full_name.split('/')
            if ':' in parts[0] and len(parts) > 1:
                return '/'.join(parts[1:])
        return image_full_name

    def extract_name_and_tag(self, image_full_name: str) -> Tuple[str, str]:
        """Extrait le nom et le tag d'une image complète"""
        normalized = self.normalize_image_name(image_full_name)
        if ':' in normalized:
            name, tag = normalized.rsplit(':', 1)
            return name, tag
        return normalized, 'latest'

    def get_image_manifest(self, image_name: str, tag: str) -> Dict:
        """Récupère le manifeste d'une image"""
        try:
            # Obtenir le manifeste
            response = requests.get(
                f"{self.base_url}/v2/{image_name}/manifests/{tag}",
                headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Erreur lors de la récupération du manifeste pour {image_name}:{tag}")
                return {}
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du manifeste: {e}")
            return {}

    def get_image_size(self, image_name: str, tag: str) -> int:
        """Récupère la taille d'une image en bytes"""
        try:
            manifest = self.get_image_manifest(image_name, tag)
            if manifest and "config" in manifest:
                config_digest = manifest["config"]["digest"]

                # Récupérer la configuration de l'image
                response = requests.get(
                    f"{self.base_url}/v2/{image_name}/blobs/{config_digest}",
                    timeout=10
                )
                if response.status_code == 200:
                    config = response.json()
                    return config.get("size", 0)
            return 0
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la taille: {e}")
            return 0

    def get_image_creation_date(self, image_name: str, tag: str) -> Optional[str]:
        """Récupère la date de création d'une image"""
        try:
            manifest = self.get_image_manifest(image_name, tag)
            if manifest and "config" in manifest:
                config_digest = manifest["config"]["digest"]

                response = requests.get(
                    f"{self.base_url}/v2/{image_name}/blobs/{config_digest}",
                    timeout=10
                )
                if response.status_code == 200:
                    config = response.json()
                    return config.get("created")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la date de création: {e}")
            return None

    def delete_image_tag(self, image_name: str, tag: str) -> bool:
        """Supprime un tag d'image du registry"""
        try:
            # Obtenir le digest du manifeste
            response = requests.get(
                f"{self.base_url}/v2/{image_name}/manifests/{tag}",
                headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                timeout=10
            )
            if response.status_code == 200:
                digest = response.headers.get("Docker-Content-Digest")
                if digest:
                    # Supprimer avec le digest
                    delete_response = requests.delete(
                        f"{self.base_url}/v2/{image_name}/manifests/{digest}",
                        timeout=10
                    )
                    return delete_response.status_code == 202
            return False
        except Exception as e:
            logger.error(f"Erreur lors de la suppression de {image_name}:{tag}: {e}")
            return False

    def get_detailed_image_info(self, image_name: str, tag: str) -> Dict:
        """Récupère les informations détaillées d'une image"""
        try:
            manifest = self.get_image_manifest(image_name, tag)
            size = self.get_image_size(image_name, tag)
            created = self.get_image_creation_date(image_name, tag)

            return {
                "name": image_name,
                "tag": tag,
                "size": size,
                "created": created,
                "manifest": manifest
            }
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos détaillées: {e}")
            return {}