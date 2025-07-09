from typing import List, Dict, Optional, Set
from app.external.k8s_client import K8sClient
import logging

logger = logging.getLogger(__name__)

class K8sService:
    def __init__(self, k8s_client: K8sClient):
        self.k8s_client = k8s_client

    def get_namespaces(self) -> List[Dict]:
        """Récupère la liste des namespaces"""
        return self.k8s_client.get_namespaces()

    def get_deployed_images(self, namespace: Optional[str] = None) -> Set[str]:
        """Récupère les images déployées"""
        return self.k8s_client.get_deployed_images(namespace)

    def get_pods(self, namespace: str = "default") -> List[Dict]:
        """Récupère les pods"""
        return self.k8s_client.get_pods(namespace)

    def get_deployments(self, namespace: str = "default") -> List[Dict]:
        """Récupère les deployments"""
        return self.k8s_client.get_deployments(namespace)

    def get_services(self, namespace: str = "default") -> List[Dict]:
        """Récupère les services"""
        return self.k8s_client.get_services(namespace)