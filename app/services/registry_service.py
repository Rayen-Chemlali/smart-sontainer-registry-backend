from typing import List, Dict, Optional, Set
from app.external.registry_client import RegistryClient
from app.external.k8s_client import K8sClient
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