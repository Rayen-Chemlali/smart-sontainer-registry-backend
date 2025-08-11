import requests
import logging
import subprocess
import time
from typing import List, Dict, Set, Tuple, Optional
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class RegistryClient:
    def __init__(self, base_url: str, container_name: str = "registry",
                 minio_endpoint: str = None, minio_access_key: str = None,
                 minio_secret_key: str = None, minio_secure: bool = False,
                 minio_bucket: str = "docker-images"):
        self.base_url = base_url
        self.container_name = container_name

        self.minio_endpoint = minio_endpoint
        self.minio_access_key = minio_access_key
        self.minio_secret_key = minio_secret_key
        self.minio_secure = minio_secure
        self.minio_bucket = minio_bucket

        self.minio_client = None
        if all([minio_endpoint, minio_access_key, minio_secret_key]):
            try:
                self.minio_client = Minio(
                    minio_endpoint,
                    access_key=minio_access_key,
                    secret_key=minio_secret_key,
                    secure=minio_secure
                )
                found = self.minio_client.bucket_exists(self.minio_bucket)
                if not found:
                    self.minio_client.make_bucket(self.minio_bucket)
                    logger.info(f"Bucket MinIO '{self.minio_bucket}' créé.")
                else:
                    logger.info(f"Bucket MinIO '{self.minio_bucket}' existe déjà.")
                logger.info("Client MinIO initialisé avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de l'initialisation du client MinIO: {e}")
                self.minio_client = None

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
        """Récupère le manifeste d'une image en gérant les manifest lists"""
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

            if "manifests" in manifest:
                first_manifest = manifest["manifests"][0]
                digest = first_manifest.get("digest")
                if not digest:
                    logger.error("Manifest list sans digest dans manifests[0]")
                    return {}

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
        """Récupère la taille totale d'une image Docker/OCI"""
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

            if "manifests" in manifest:
                first_manifest = manifest["manifests"][0]
                digest = first_manifest.get("digest")
                if not digest:
                    logger.error("Manifest list sans digest dans manifests[0]")
                    return 0

                response = requests.get(
                    f"{self.base_url}/v2/{image_name}/manifests/{digest}",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"Erreur HTTP {response.status_code} lors de la récupération du manifest enfant")
                    return 0
                manifest = response.json()

            layers = manifest.get("layers", [])
            total_size = sum(layer.get("size", 0) for layer in layers)
            return total_size

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la taille: {e}")
            return 0

    def get_manifest_last_modified(self, image_name: str, reference: str) -> Optional[str]:
        """Récupère la date de dernière modification d'un manifest"""
        try:
            headers = {
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.oci.image.manifest.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json"
                )
            }
            response = requests.head(
                f"{self.base_url}/v2/{image_name}/manifests/{reference}",
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                last_modified = (
                        response.headers.get("Last-Modified") or
                        response.headers.get("Date") or
                        response.headers.get("last-modified")
                )
                return last_modified
            return None
        except Exception as e:
            return None

    def get_image_layers_details(self, image_name: str, reference: str) -> List[Dict]:
        """Récupère les détails de base des layers d'une image"""
        try:
            manifest = self.get_image_manifest(image_name, reference)

            if not manifest or "layers" not in manifest:
                return []

            layers_details = []

            for i, layer in enumerate(manifest["layers"]):
                layer_digest = layer.get("digest")
                layer_size = layer.get("size", 0)
                layer_media_type = layer.get("mediaType", "unknown")

                layer_info = {
                    "index": i,
                    "digest": layer_digest,
                    "size": layer_size,
                    "size_mb": round(layer_size / (1024 * 1024), 2) if layer_size else 0,
                    "mediaType": layer_media_type
                }

                layers_details.append(layer_info)

            return layers_details

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des détails des layers: {e}")
            return []

    def get_detailed_image_info(self, image_name: str, tag: str) -> Dict:
        """Récupère les informations détaillées d'une image"""
        try:
            manifest = self.get_image_manifest(image_name, tag)
            size = self.get_image_size(image_name, tag)
            manifest_last_modified = self.get_manifest_last_modified(image_name, tag)
            layers_details = self.get_image_layers_details(image_name, tag)

            return {
                "name": image_name,
                "tag": tag,
                "size": size,
                "size_mb": round(size / (1024 * 1024), 2) if size else 0,
                "created": None,
                "last_modified": manifest_last_modified,
                "digest": manifest.get("config", {}).get("digest") if manifest else None,
                "layers": layers_details,
                "layer_count": len(layers_details),
                "config": manifest.get("config", {}) if manifest else {},
                "architecture": None,
                "os": None
            }
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos détaillées: {e}")
            return {
                "name": image_name,
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
                "os": None
            }

    def delete_image_tag(self, image_name: str, tag: str) -> bool:
        """Supprime un tag d'image du registry"""
        try:
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

    def force_garbage_collection(self) -> bool:
        """Force le garbage collection via docker exec"""
        try:
            logger.info("Déclenchement du garbage collection...")

            cmd = [
                "docker", "exec", self.container_name,
                "/bin/registry", "garbage-collect", "/etc/docker/registry/config.yml"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                logger.info("Garbage collection terminé avec succès")
                logger.debug(f"Sortie GC: {result.stdout}")
                return True
            else:
                logger.error(f"Erreur lors du garbage collection: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Timeout lors du garbage collection")
            return False
        except Exception as e:
            logger.error(f"Erreur lors du garbage collection: {e}")
            return False

    def cleanup_minio_objects(self, image_name: str) -> Dict:
        """Nettoie directement les objets MinIO pour une image"""
        if not self.minio_client:
            return {"deleted_objects": [], "errors": ["Client MinIO non initialisé"], "success": False,
                    "total_deleted": 0}

        try:
            logger.info(f"Nettoyage MinIO pour l'image {image_name}")

            deleted_objects = []
            errors = []

            prefix = f"docker/registry/v2/repositories/{image_name}/"

            try:
                objects = list(self.minio_client.list_objects(self.minio_bucket, prefix=prefix, recursive=True))

                if not objects:
                    logger.info(f"Aucun objet trouvé dans MinIO pour {image_name}")
                    return {"deleted_objects": [], "errors": [], "success": True, "total_deleted": 0}

                logger.info(f"Trouvé {len(objects)} objets à supprimer pour {image_name}")

                for obj in objects:
                    try:
                        self.minio_client.remove_object(self.minio_bucket, obj.object_name)
                        deleted_objects.append(obj.object_name)
                        logger.info(f"✅ Supprimé: {obj.object_name}")
                    except S3Error as e:
                        error_msg = f"Erreur suppression {obj.object_name}: {e}"
                        errors.append(error_msg)
                        logger.error(f"❌ {error_msg}")

            except S3Error as e:
                error_msg = f"Erreur lors de la liste des objets: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

            success = len(deleted_objects) > 0 and len(errors) == 0

            return {
                "deleted_objects": deleted_objects,
                "errors": errors,
                "success": success,
                "total_deleted": len(deleted_objects)
            }

        except Exception as e:
            logger.error(f"Erreur générale lors du nettoyage MinIO: {e}")
            return {
                "deleted_objects": [],
                "errors": [str(e)],
                "success": False,
                "total_deleted": 0
            }

    def delete_entire_image(self, image_name: str, tags: List[str], bucket_name: str = "docker-registry") -> Dict:
        """Supprime une image complète avec nettoyage automatique du registre et de MinIO"""
        deleted_tags = []
        errors = []
        minio_result = None

        logger.info(f"Début de suppression de l'image {image_name} avec {len(tags)} tags")

        for tag in tags:
            try:
                logger.info(f"Suppression du tag {image_name}:{tag}")
                success = self.delete_image_tag(image_name, tag)

                if success:
                    deleted_tags.append(tag)
                    logger.info(f"Tag {image_name}:{tag} supprimé avec succès")
                else:
                    error_msg = f"Échec de suppression du tag {image_name}:{tag}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            except Exception as e:
                error_msg = f"Erreur lors de la suppression du tag {image_name}:{tag}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)

        time.sleep(2)

        gc_success = self.force_garbage_collection()

        time.sleep(2)

        logger.info("🪣 Étape 3: Nettoyage MinIO")
        time.sleep(2)
        minio_result = self.cleanup_minio_objects(image_name)

        logger.info("🔍 Étape 4: Vérification finale")
        time.sleep(2)
        remaining_tags = self.get_image_tags(image_name)
        catalog = self.get_catalog()
        image_in_catalog = image_name in catalog

        registry_success = len(deleted_tags) == len(tags)
        minio_success = minio_result["success"] if minio_result else False
        no_remaining_tags = len(remaining_tags) == 0
        not_in_catalog = not image_in_catalog

        overall_success = registry_success and no_remaining_tags and not_in_catalog

        if overall_success:
            if minio_success:
                message = f"✅ Image {image_name} supprimée complètement (Registry + MinIO)"
            else:
                message = f"✅ Image {image_name} supprimée du Registry (MinIO: {minio_result.get('total_deleted', 0) if minio_result else 0} objets)"
        else:
            message = f"⚠️ Suppression partielle de {image_name}"

        result = {
            "success": overall_success,
            "message": message,
            "deleted_tags": deleted_tags,
            "errors": errors,
            "remaining_tags": remaining_tags,
            "image_in_catalog": image_in_catalog,
            "garbage_collection_success": gc_success,
            "minio_cleanup": minio_result,
            "steps": {
                "registry_api": registry_success,
                "garbage_collection": gc_success,
                "minio_cleanup": minio_success,
                "final_verification": not_in_catalog and no_remaining_tags
            }
        }

        if overall_success:
            logger.info(f"🎉 Image {image_name} supprimée avec succès!")
        else:
            logger.warning(f"⚠️ Suppression incomplète de {image_name}")
            if remaining_tags:
                logger.warning(f"Tags restants: {remaining_tags}")
            if image_in_catalog:
                logger.warning(f"Image encore dans le catalogue")

        return result