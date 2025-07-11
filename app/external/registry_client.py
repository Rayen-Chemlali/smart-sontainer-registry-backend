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

    def get_image_manifest(self, image_name: str, reference: str) -> Dict:
        """
        Récupère le manifeste d'une image en gérant les manifest lists.
        Retourne le manifest final (pas l'index).
        """
        try:
            headers = {
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.oci.image.manifest.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json"
                )
            }
            url = f"{self.base_url}/v2/{image_name}/manifests/{reference}"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Erreur HTTP {response.status_code} lors de la récupération du manifest")
                return {}

            manifest = response.json()

            # Si c'est un index (manifest list), récupérer le manifest spécifique
            if "manifests" in manifest:
                # Prendre le premier manifest disponible
                first_manifest = manifest["manifests"][0]
                digest = first_manifest.get("digest")
                if not digest:
                    logger.error("Manifest list sans digest dans manifests[0]")
                    return {}

                # Récupérer le manifest spécifique
                response = requests.get(
                    f"{self.base_url}/v2/{image_name}/manifests/{digest}",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"Erreur HTTP {response.status_code} lors de la récupération du manifest enfant")
                    return {}
                manifest = response.json()

            return manifest

        except Exception as e:
            logger.error(f"Erreur lors de la récupération du manifeste: {e}")
            return {}

    def get_image_size(self, image_name: str, reference: str) -> int:
        """
        Récupère la taille totale (en bytes) d'une image Docker/OCI sur un registre,
        en supportant les manifest lists (index) multi-plateformes.
        """
        try:
            headers = {
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.oci.image.manifest.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json"
                )
            }
            url = f"{self.base_url}/v2/{image_name}/manifests/{reference}"
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"Erreur HTTP {response.status_code} lors de la récupération du manifest")
                return 0

            manifest = response.json()

            # Si c'est un index (manifest list)
            if "manifests" in manifest:
                # Choisir un manifest selon une plateforme (ex: amd64/linux) - ici on prend le premier
                first_manifest = manifest["manifests"][0]
                digest = first_manifest.get("digest")
                if not digest:
                    logger.error("Manifest list sans digest dans manifests[0]")
                    return 0

                # Récupérer le manifest spécifique
                response = requests.get(
                    f"{self.base_url}/v2/{image_name}/manifests/{digest}",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"Erreur HTTP {response.status_code} lors de la récupération du manifest enfant")
                    return 0
                manifest = response.json()

            # Maintenant manifest doit contenir les layers
            layers = manifest.get("layers", [])
            total_size = sum(layer.get("size", 0) for layer in layers)
            return total_size

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la taille: {e}")
            return 0

    def get_image_creation_date(self, image_name: str, reference: str) -> Optional[str]:
        """
        Récupère la date de création d'une image en gérant les manifest lists.
        """
        try:
            # Récupérer le manifest (gère automatiquement les manifest lists)
            manifest = self.get_image_manifest(image_name, reference)

            if not manifest or "config" not in manifest:
                logger.warning(f"Pas de config trouvée dans le manifest pour {image_name}:{reference}")
                return None

            config_digest = manifest["config"]["digest"]
            if not config_digest:
                logger.warning(f"Pas de digest config pour {image_name}:{reference}")
                return None

            logger.info(f"Tentative de récupération de la config avec digest: {config_digest}")

            # Récupérer la configuration de l'image avec les headers appropriés
            headers = {
                "Accept": "application/vnd.oci.image.config.v1+json, application/vnd.docker.container.image.v1+json"
            }
            response = requests.get(
                f"{self.base_url}/v2/{image_name}/blobs/{config_digest}",
                headers=headers,
                timeout=10
            )

            logger.info(
                f"Réponse config: status={response.status_code}, content-type={response.headers.get('content-type')}")

            if response.status_code == 200:
                try:
                    config = response.json()
                    logger.info(f"Config récupérée, clés disponibles: {list(config.keys())}")

                    # Essayer différents champs pour la date de création
                    created_date = (
                            config.get("created") or
                            config.get("Created") or
                            config.get("config", {}).get("created") or
                            config.get("config", {}).get("Created")
                    )

                    if created_date:
                        logger.info(f"Date de création trouvée: {created_date}")
                        return created_date
                    else:
                        logger.warning(f"Pas de date 'created' dans la config pour {image_name}:{reference}")
                        # Log du contenu pour debug
                        logger.debug(f"Contenu de la config: {config}")
                        return None
                except Exception as json_error:
                    logger.error(f"Erreur lors du parsing JSON de la config: {json_error}")
                    logger.debug(f"Contenu de la réponse: {response.text[:500]}")
                    return None
            else:
                logger.error(f"Erreur HTTP {response.status_code} lors de la récupération de la config")
                logger.debug(f"Réponse: {response.text[:200]}")
                return None

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la date de création: {e}")
            return None

    def delete_image_tag(self, image_name: str, tag: str) -> bool:
        """Supprime un tag d'image du registry"""
        try:
            # Obtenir le digest du manifeste
            headers = {
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.oci.image.manifest.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json"
                )
            }
            response = requests.get(
                f"{self.base_url}/v2/{image_name}/manifests/{tag}",
                headers=headers,
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
                else:
                    logger.error(f"Pas de Docker-Content-Digest dans la réponse pour {image_name}:{tag}")
                    return False
            else:
                logger.error(f"Erreur HTTP {response.status_code} lors de la récupération du manifest pour suppression")
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
            return {
                "name": image_name,
                "tag": tag,
                "size": 0,
                "created": None,
                "manifest": {}
            }