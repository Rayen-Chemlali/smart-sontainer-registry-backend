from kubernetes import client, config
import logging
from typing import List, Dict, Set, Optional

logger = logging.getLogger(__name__)


class K8sClient:
    def __init__(self):
        try:
            config.load_incluster_config()
        except:
            try:
                config.load_kube_config()
            except Exception as e:
                logger.error(f"Impossible de charger la configuration Kubernetes: {e}")
                raise

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def get_namespaces(self) -> List[Dict]:
        """Récupère la liste des namespaces"""
        try:
            namespaces = self.v1.list_namespace()
            return [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                    "created": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
                }
                for ns in namespaces.items
            ]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des namespaces: {e}")
            return []

    def get_deployed_images(self, namespace: Optional[str] = None) -> Set[str]:
        """Récupère toutes les images déployées dans le cluster"""
        deployed_images = set()

        try:
            # Récupérer les images des pods
            if namespace:
                pods = self.v1.list_namespaced_pod(namespace)
            else:
                pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                for container in pod.spec.containers:
                    if container.image:
                        deployed_images.add(container.image)
                        logger.info(f"Image trouvée dans pod {pod.metadata.name}: {container.image}")

                if pod.spec.init_containers:
                    for init_container in pod.spec.init_containers:
                        if init_container.image:
                            deployed_images.add(init_container.image)

            # Récupérer les images des deployments
            if namespace:
                deployments = self.apps_v1.list_namespaced_deployment(namespace)
            else:
                deployments = self.apps_v1.list_deployment_for_all_namespaces()

            for deployment in deployments.items:
                for container in deployment.spec.template.spec.containers:
                    if container.image:
                        deployed_images.add(container.image)

                if deployment.spec.template.spec.init_containers:
                    for init_container in deployment.spec.template.spec.init_containers:
                        if init_container.image:
                            deployed_images.add(init_container.image)

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images déployées: {e}")

        return deployed_images

    def get_pods(self, namespace: str = "default") -> List[Dict]:
        """Récupère la liste des pods"""
        try:
            pods = self.v1.list_namespaced_pod(namespace)
            return [
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "node": pod.spec.node_name,
                    "created": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                    "containers": [
                        {
                            "name": container.name,
                            "image": container.image,
                            "ready": any(
                                cs.name == container.name and cs.ready for cs in (pod.status.container_statuses or []))
                        }
                        for container in pod.spec.containers
                    ]
                }
                for pod in pods.items
            ]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des pods: {e}")
            return []

    def get_deployments(self, namespace: str = "default") -> List[Dict]:
        """Récupère la liste des deployments"""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
            return [
                {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "replicas": deployment.spec.replicas,
                    "ready_replicas": deployment.status.ready_replicas or 0,
                    "available_replicas": deployment.status.available_replicas or 0,
                    "created": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None,
                    "images": list(set([container.image for container in deployment.spec.template.spec.containers]))
                }
                for deployment in deployments.items
            ]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des deployments: {e}")
            return []

    def get_services(self, namespace: str = "default") -> List[Dict]:
        """Récupère la liste des services"""
        try:
            services = self.v1.list_namespaced_service(namespace)
            return [
                {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "ports": [
                        {
                            "port": port.port,
                            "target_port": str(port.target_port) if port.target_port else None,
                            "protocol": port.protocol
                        }
                        for port in (service.spec.ports or [])
                    ],
                    "created": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None
                }
                for service in services.items
            ]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des services: {e}")
            return []