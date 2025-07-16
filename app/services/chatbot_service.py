from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.external.groq_client import GroqClient
from app.services.registry_service import RegistryService
from app.services.k8s_service import K8sService
from app.services.overview_service import OverviewService
from app.external.s3_client import S3Client
import logging

logger = logging.getLogger(__name__)


class ChatbotService:
    def __init__(
            self,
            groq_client: GroqClient,
            registry_service: RegistryService,
            k8s_service: K8sService,
            overview_service: OverviewService,
            s3_client: S3Client
    ):
        self.groq_client = groq_client
        self.registry_service = registry_service
        self.k8s_service = k8s_service
        self.overview_service = overview_service
        self.s3_client = s3_client

    async def process_message(self, user_message: str, context: Optional[Dict] = None) -> Dict:
        """Traite un message utilisateur et retourne la réponse"""

        # Analyser l'intention de l'utilisateur
        intent = self.groq_client.analyze_user_intent(user_message, context)

        logger.info(f"Intent analysé: {intent}")

        # Exécuter l'action appropriée
        try:
            data = await self._execute_action(intent["action"], intent["parameters"])

            # Générer une réponse naturelle
            response = self.groq_client.generate_response(data, intent["action"], user_message)

            return {
                "user_message": user_message,
                "intent": intent,
                "data": data,
                "response": response,
                "success": True,
                "is_markdown": True
            }

        except Exception as e:
            logger.error(f"Erreur exécution action: {e}")
            return {
                "user_message": user_message,
                "intent": intent,
                "data": None,
                "response": f"## ❌ Erreur\n\nDésolé, j'ai rencontré une erreur lors de l'exécution:\n\n```\n{str(e)}\n```",
                "success": False,
                "error": str(e),
                "is_markdown": True
            }

    async def _execute_action(self, action: str, parameters: Dict) -> Any:
        """Exécute l'action déterminée par l'IA"""

        namespace = parameters.get("namespace")
        image_name = parameters.get("image_name")
        bucket_name = parameters.get("bucket_name")
        tag = parameters.get("tag")
        days_old = parameters.get("days_old")
        deployed = parameters.get("deployed")
        force = parameters.get("force", False)

        if action == "list_images":
            return self.registry_service.get_images_with_deployment_status(namespace)

        elif action == "list_pods":
            return self.k8s_service.get_pods(namespace or "default")

        elif action == "list_deployments":
            return self.k8s_service.get_deployments(namespace or "default")

        elif action == "list_namespaces":
            return self.k8s_service.get_namespaces()

        elif action == "get_overview":
            return self.overview_service.get_complete_overview()

        elif action == "get_deployed_images":
            deployed_images = self.k8s_service.get_deployed_images(namespace)
            return {
                "namespace": namespace or "all",
                "deployed_images": list(deployed_images),
                "count": len(deployed_images)
            }

        elif action == "get_s3_buckets":
            buckets = self.s3_client.get_buckets()
            if bucket_name:
                bucket_objects = self.s3_client.get_objects_in_bucket(bucket_name)
                return {
                    "buckets": buckets,
                    "requested_bucket": bucket_name,
                    "objects": bucket_objects
                }
            return {"buckets": buckets}

        elif action == "list_services":
            return self.k8s_service.get_services(namespace or "default")

        elif action == "get_image_details":
            if not image_name:
                return {"error": "Nom d'image requis pour obtenir les détails."}
            if not tag:
                return {"action_required": "ask_for_tag", "image_name": image_name,
                        "message": f"Veuillez spécifier le tag pour l'image {image_name}."}
            return self.registry_service.get_detailed_image_info(image_name, tag)
        elif action == "delete_image":
            if not image_name:
                return {"error": "Nom d'image requis pour la suppression."}
            if not tag:
                return {"action_required": "ask_for_tag", "image_name": image_name,
                        "message": f"Veuillez spécifier le tag pour l'image {image_name} que vous souhaitez supprimer."}

            # Récupérer les tags si non spécifiés
            tags_to_delete = [tag] if tag else self.registry_service.get_image_tags(image_name)
            if not tags_to_delete:
                return {"message": f"Aucun tag trouvé pour l'image {image_name}, rien à supprimer."}

            # Logique de suppression basée sur les paramètres
            if days_old is not None or deployed is not None:
                # Filtrer les images selon les critères
                all_images = self.registry_service.get_images_with_deployment_status()
                images_to_consider = [img for img in all_images if img["name"] == image_name]

                if not images_to_consider:
                    return {"message": f"Image {image_name} non trouvée ou ne correspond pas aux critères."}

                filtered_tags = []
                for img_info in images_to_consider:
                    for t in img_info["tags"]:
                        # Vérifier l'âge
                        if days_old is not None:
                            created_date_str = self.registry_service.get_image_creation_date(image_name, t["tag"])
                            if created_date_str:
                                created_date = datetime.fromisoformat(created_date_str.replace('Z', '+00:00'))
                                if (datetime.now(timezone.utc) - created_date).days < days_old:
                                    continue  # Trop jeune

                        # Vérifier le statut de déploiement
                        if deployed is not None:
                            is_deployed_tag = t["tag"] in img_info["deployed_tags"]
                            # if is_deployed != is_deployed_tag:
                            #     continue  # Ne correspond pas au statut de déploiement

                        filtered_tags.append(t["tag"])

                if not filtered_tags:
                    return {"message": f"Aucun tag de {image_name} ne correspond aux critères de suppression."}

                tags_to_delete = filtered_tags

            if not tags_to_delete:
                return {"message": f"Aucun tag à supprimer pour l'image {image_name} avec les critères spécifiés."}

            # Demander confirmation si 'force' n'est pas True
            if not force:
                return {
                    "action_required": "confirm_delete",
                    "image_name": image_name,
                    "tags_to_delete": tags_to_delete,
                    "message": f"Confirmez-vous la suppression de l'image {image_name} avec les tags: {', '.join(tags_to_delete)}? (Répondez 'oui' pour confirmer)"
                }
            else:
                # Exécuter la suppression
                return self.registry_service.delete_entire_image(image_name, tags_to_delete)
        elif action == "compare_registry_deployment":
            images = self.registry_service.get_images_with_deployment_status(namespace)
            deployed_count = len([img for img in images if img["is_deployed"]])

            return {
                "total_images": len(images),
                "deployed_images": deployed_count,
                "not_deployed_images": len(images) - deployed_count,
                "deployment_rate": f"{(deployed_count / len(images) * 100):.1f}%" if images else "0%",
                "images_breakdown": [
                    {
                        "name": img["name"],
                        "is_deployed": img["is_deployed"],
                        "tags_count": img["tag_count"],
                        "deployed_tags": img["deployed_tags"]
                    }
                    for img in images
                ]
            }

        elif action == "general_info":
            return {
                "message": "Je suis votre assistant pour la gestion des registres de conteneurs et Kubernetes.",
                "available_commands": [
                    "Lister les images du registre",
                    "Afficher les pods et deployments",
                    "Voir les namespaces",
                    "Obtenir une vue d'ensemble",
                    "Comparer registre et déploiements",
                    "Gérer les buckets S3"
                ],
                "examples": [
                    "Liste-moi toutes les images",
                    "Montre-moi les pods du namespace production",
                    "Quelles images sont déployées?",
                    "Donne-moi une vue d'ensemble",
                    "Compare le registre et les déploiements"
                ],
                "markdown_ready": True
            }

        else:
            return {"error": f"Action '{action}' non reconnue"}