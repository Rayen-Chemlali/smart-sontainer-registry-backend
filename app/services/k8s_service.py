from typing import List, Dict, Optional, Set, Any
from app.external.k8s_client import K8sClient
from app.core.decorators import chatbot_function
import logging

logger = logging.getLogger(__name__)


class K8sService:
    def __init__(self, k8s_client: K8sClient):
        self.k8s_client = k8s_client

    @chatbot_function(
        name="get_k8s_namespaces",
        description="Récupère la liste complète des namespaces Kubernetes disponibles dans le cluster",
        examples=[
            "Quels sont les namespaces disponibles ?",
            "Liste-moi tous les namespaces",
            "Montre-moi les espaces de noms Kubernetes"
        ]
    )
    def get_namespaces(self) -> List[Dict]:
        """Récupère la liste des namespaces Kubernetes"""
        try:
            namespaces = self.k8s_client.get_namespaces()
            logger.info(f"Récupération de {len(namespaces)} namespaces")
            return namespaces
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des namespaces: {e}")
            raise

    @chatbot_function(
        name="get_deployed_images",
        description="Récupère toutes les images de conteneurs déployées dans le cluster ou un namespace spécifique",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "default": None,
                "description": "Namespace spécifique (optionnel, par défaut tous les namespaces)"
            }
        },
        examples=[
            "Quelles images sont déployées ?",
            "Montre-moi les images dans le namespace production",
            "Liste des conteneurs déployés"
        ]
    )
    def get_deployed_images(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Récupère les images déployées avec informations détaillées"""
        try:
            images_set = self.k8s_client.get_deployed_images(namespace)
            images_list = list(images_set)

            result = {
                "images": images_list,
                "total_count": len(images_list),
                "namespace": namespace or "tous les namespaces",
                "unique_registries": list(
                    set([img.split('/')[0] if '/' in img else 'docker.io' for img in images_list]))
            }

            logger.info(f"Récupération de {len(images_list)} images déployées")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images: {e}")
            raise

    @chatbot_function(
        name="get_k8s_pods",
        description="Récupère la liste des pods dans un namespace spécifique avec leur statut et informations",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "default": "default",
                "description": "Nom du namespace (par défaut: default)"
            }
        },
        examples=[
            "Montre-moi les pods du namespace production",
            "Quels sont les pods en cours d'exécution ?",
            "Liste des pods dans default"
        ]
    )
    def get_pods(self, namespace: str = "default") -> Dict[str, Any]:
        """Récupère les pods avec informations détaillées"""
        try:
            pods = self.k8s_client.get_pods(namespace)

            result = {
                "namespace": namespace,
                "pods": pods,
                "total_count": len(pods),
                "status_summary": self._get_pods_status_summary(pods),
                "images_used": list(set([
                    container.get('image', '')
                    for pod in pods
                    for container in pod.get('containers', [])
                    if container.get('image')
                ]))
            }

            logger.info(f"Récupération de {len(pods)} pods dans le namespace {namespace}")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des pods: {e}")
            raise

    @chatbot_function(
        name="get_k8s_deployments",
        description="Récupère la liste des deployments avec leur état et configuration dans un namespace",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "default": "default",
                "description": "Nom du namespace (par défaut: default)"
            }
        },
        examples=[
            "Montre-moi les deployments",
            "Quels sont les déploiements dans production ?",
            "État des deployments Kubernetes"
        ]
    )
    def get_deployments(self, namespace: str = "default") -> Dict[str, Any]:
        """Récupère les deployments avec informations détaillées"""
        try:
            deployments_raw = self.k8s_client.get_deployments(namespace)

            # Transform the data to match the expected structure
            deployments = []
            for deployment in deployments_raw:
                deployments.append({
                    "name": deployment.get("name"),
                    "namespace": deployment.get("namespace"),
                    "replicas": deployment.get("replicas", 0),
                    "ready_replicas": deployment.get("ready_replicas", 0),
                    "available_replicas": deployment.get("available_replicas", 0),
                    "created": deployment.get("created"),
                    "images": deployment.get("images", [])
                })

            result = {
                "namespace": namespace,
                "deployments": deployments,
                "total_count": len(deployments),
                "ready_count": len([d for d in deployments if d.get("ready_replicas", 0) == d.get("replicas", 0)]),
                "images_used": list(set([
                    image
                    for deployment in deployments
                    for image in deployment.get("images", [])
                    if image
                ]))
            }

            logger.info(f"Récupération de {len(deployments)} deployments dans le namespace {namespace}")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des deployments: {e}")
            raise

    @chatbot_function(
        name="get_k8s_services",
        description="Récupère la liste des services Kubernetes avec leurs endpoints et configuration",
        parameters_schema={
            "namespace": {
                "type": "str",
                "required": False,
                "default": "default",
                "description": "Nom du namespace (par défaut: default)"
            }
        },
        examples=[
            "Quels sont les services exposés ?",
            "Montre-moi les services dans le namespace web",
            "Liste des endpoints disponibles"
        ]
    )
    def get_services(self, namespace: str = "default") -> Dict[str, Any]:
        """Récupère les services avec informations détaillées"""
        try:
            services = self.k8s_client.get_services(namespace)

            result = {
                "namespace": namespace,
                "services": services,
                "total_count": len(services),
                "service_types": list(set([s.get('type', 'Unknown') for s in services])),
                "exposed_ports": [
                    port for service in services
                    for port in service.get('ports', [])
                ]
            }

            logger.info(f"Récupération de {len(services)} services dans le namespace {namespace}")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des services: {e}")
            raise

    @chatbot_function(
        name="get_cluster_overview",
        description="Fournit une vue d'ensemble complète du cluster Kubernetes avec statistiques générales",
        examples=[
            "Donne-moi un aperçu du cluster",
            "Résumé de l'état du cluster Kubernetes",
            "Vue d'ensemble de l'infrastructure"
        ]
    )
    def get_cluster_overview(self) -> Dict[str, Any]:
        """Récupère une vue d'ensemble du cluster"""
        try:
            # Récupérer les données de base
            namespaces = self.get_namespaces()
            all_images = self.get_deployed_images()

            # Calculer les statistiques pour chaque namespace
            namespace_stats = []
            total_pods = 0
            total_deployments = 0
            total_services = 0

            for ns in namespaces:
                ns_name = ns.get('name', '')
                if ns_name not in ['kube-system', 'kube-public', 'kube-node-lease']:
                    try:
                        pods = self.k8s_client.get_pods(ns_name)
                        deployments = self.k8s_client.get_deployments(ns_name)
                        services = self.k8s_client.get_services(ns_name)

                        namespace_stats.append({
                            "name": ns_name,
                            "pods_count": len(pods),
                            "deployments_count": len(deployments),
                            "services_count": len(services)
                        })

                        total_pods += len(pods)
                        total_deployments += len(deployments)
                        total_services += len(services)

                    except Exception as e:
                        logger.warning(f"Erreur lors de la récupération des stats pour {ns_name}: {e}")

            result = {
                "cluster_summary": {
                    "total_namespaces": len(namespaces),
                    "user_namespaces": len(namespace_stats),
                    "total_pods": total_pods,
                    "total_deployments": total_deployments,
                    "total_services": total_services,
                    "unique_images": all_images["total_count"],
                    "registries": all_images["unique_registries"]
                },
                "namespace_details": namespace_stats,
                "health_indicators": {
                    "namespaces_accessible": len(namespace_stats),
                    "images_diversity": len(all_images["unique_registries"]),
                    "avg_pods_per_namespace": round(total_pods / max(len(namespace_stats), 1), 1)
                }
            }

            logger.info("Vue d'ensemble du cluster générée avec succès")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la génération de la vue d'ensemble: {e}")
            raise

    @chatbot_function(
        name="search_resources_by_image",
        description="Recherche tous les pods et deployments utilisant une image spécifique",
        parameters_schema={
            "image_name": {
                "type": "str",
                "required": True,
                "description": "Nom ou partie du nom de l'image à rechercher"
            },
            "namespace": {
                "type": "str",
                "required": False,
                "default": None,
                "description": "Namespace spécifique à rechercher (optionnel)"
            }
        },
        examples=[
            "Où est utilisée l'image nginx ?",
            "Recherche l'image mysql dans le cluster",
            "Quels pods utilisent l'image redis ?"
        ]
    )
    def search_resources_by_image(self, image_name: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Recherche les ressources utilisant une image spécifique"""
        try:
            matching_pods = []
            matching_deployments = []

            # Déterminer les namespaces à rechercher
            if namespace:
                namespaces_to_search = [{"name": namespace}]
            else:
                namespaces_to_search = self.get_namespaces()

            for ns in namespaces_to_search:
                ns_name = ns.get('name', '')
                try:
                    # Rechercher dans les pods
                    pods = self.k8s_client.get_pods(ns_name)
                    for pod in pods:
                        for container in pod.get('containers', []):
                            if image_name.lower() in container.get('image', '').lower():
                                matching_pods.append({
                                    **pod,
                                    "namespace": ns_name,
                                    "matching_image": container.get('image')
                                })

                    # Rechercher dans les deployments
                    deployments = self.k8s_client.get_deployments(ns_name)
                    for deployment in deployments:
                        for container in deployment.get('containers', []):
                            if image_name.lower() in container.get('image', '').lower():
                                matching_deployments.append({
                                    **deployment,
                                    "namespace": ns_name,
                                    "matching_image": container.get('image')
                                })

                except Exception as e:
                    logger.warning(f"Erreur lors de la recherche dans {ns_name}: {e}")

            result = {
                "search_term": image_name,
                "search_scope": namespace or "tous les namespaces",
                "matching_pods": matching_pods,
                "matching_deployments": matching_deployments,
                "total_matches": len(matching_pods) + len(matching_deployments),
                "unique_images_found": list(set([
                                                    pod["matching_image"] for pod in matching_pods
                                                ] + [
                                                    dep["matching_image"] for dep in matching_deployments
                                                ]))
            }

            logger.info(f"Recherche d'image '{image_name}': {result['total_matches']} correspondances trouvées")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la recherche d'image: {e}")
            raise

    def _get_pods_status_summary(self, pods: List[Dict]) -> Dict[str, int]:
        """Calcule un résumé des statuts des pods"""
        status_count = {}
        for pod in pods:
            status = pod.get('status', 'Unknown')
            status_count[status] = status_count.get(status, 0) + 1
        return status_count