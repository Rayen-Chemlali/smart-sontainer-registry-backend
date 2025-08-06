from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import logging
from app.external.groq_client import GroqClient
from app.core.function_registry import FunctionRegistry
from app.api.schemas.chatbot import ServiceNavigation, ConfirmationRequired

logger = logging.getLogger(__name__)


class ChatbotService:
    def __init__(self, groq_client: GroqClient, function_registry: FunctionRegistry):
        self.groq_client = groq_client
        self.function_registry = function_registry
        self.pending_actions = {}  # Store pour les actions en attente de confirmation

    def _get_service_navigation(self, service_name: str) -> Optional[ServiceNavigation]:
        """Retourne les informations de navigation pour un service"""
        service_mappings = {
            "kubernetes": ServiceNavigation(
                service_name="kubernetes",
                display_name="Kubernetes",
                dashboard_route="/dashboard/kubernetes",
                icon="server",
                description="Gérer vos pods, deployments et services"
            ),
            "registry": ServiceNavigation(
                service_name="registry",
                display_name="Container Registry",
                dashboard_route="/dashboard/registry",
                icon="package",
                description="Explorer et gérer vos images de conteneurs"
            ),
            "docker_registry": ServiceNavigation(  # 🔥 AJOUT: Alias pour docker_registry
                service_name="docker_registry",
                display_name="Container Registry",
                dashboard_route="/dashboard/registry",
                icon="package",
                description="Explorer et gérer vos images de conteneurs"
            ),
            "rules_engine": ServiceNavigation(  # 🔥 AJOUT CRITIQUE
                service_name="rules_engine",
                display_name="Rules Engine",
                dashboard_route="/dashboard/rules",
                icon="settings",
                description="Configurer les règles automatiques"
            ),
            "overview": ServiceNavigation(
                service_name="overview",
                display_name="Vue d'ensemble",
                dashboard_route="/dashboard/overview",
                icon="layout-dashboard",
                description="Vue globale de votre infrastructure"
            ),
            "s3": ServiceNavigation(
                service_name="s3",
                display_name="Stockage S3",
                dashboard_route="/dashboard/storage",
                icon="hard-drive",
                description="Gérer vos buckets et fichiers"
            )
        }
        return service_mappings.get(service_name)
        return service_mappings.get(service_name)

    def _requires_confirmation(self, function_name: str, parameters: Dict) -> Optional[ConfirmationRequired]:
        """Détermine si une action nécessite une confirmation utilisateur"""

        # Actions de suppression
        if any(keyword in function_name.lower() for keyword in ['delete', 'remove', 'purge', 'cleanup']):
            action_type = "delete"
            warning_message = "⚠️ Cette action va supprimer des éléments de manière permanente."
            confirmation_text = "Êtes-vous sûr de vouloir continuer ?"

            # Messages spécifiques selon le type
            if 'image' in function_name.lower():
                warning_message = "⚠️ Cette action va supprimer définitivement des images de conteneurs."
                confirmation_text = "Confirmer la suppression des images ?"
            elif 'pod' in function_name.lower():
                warning_message = "⚠️ Cette action va arrêter et supprimer des pods."
                confirmation_text = "Confirmer la suppression des pods ?"
            elif 'deployment' in function_name.lower():
                warning_message = "⚠️ Cette action va supprimer des deployments actifs."
                confirmation_text = "Confirmer la suppression des deployments ?"

            return ConfirmationRequired(
                required=True,
                action_type=action_type,
                warning_message=warning_message,
                confirmation_text=confirmation_text,
                preview_data=parameters
            )

        # Actions de modification critiques
        if any(keyword in function_name.lower() for keyword in ['update', 'modify', 'scale', 'restart']):
            if 'scale' in function_name.lower():
                replicas = parameters.get('replicas', 'N/A')
                return ConfirmationRequired(
                    required=True,
                    action_type="modify",
                    warning_message=f"⚠️ Cette action va modifier le nombre de replicas à {replicas}.",
                    confirmation_text="Confirmer la modification ?",
                    preview_data=parameters
                )
            elif 'restart' in function_name.lower():
                return ConfirmationRequired(
                    required=True,
                    action_type="modify",
                    warning_message="⚠️ Cette action va redémarrer des services.",
                    confirmation_text="Confirmer le redémarrage ?",
                    preview_data=parameters
                )

        return None

    async def process_message(self, user_message: str, context: Optional[Dict] = None) -> Dict:
        """Traite un message utilisateur avec sélection de service optimisée"""
        try:
            # Étape 1: Sélectionner le meilleur service
            available_services = self.function_registry.get_available_services_info()
            selected_service = self.groq_client.select_best_service(user_message, available_services)

            logger.info(f"Service sélectionné: {selected_service}")

            # Étape 2: Obtenir les fonctions du service sélectionné
            service_functions = self.function_registry.get_functions_for_service(selected_service)

            # Étape 3: Analyser l'intention pour ce service spécifique
            intent = self.groq_client.analyze_user_intent_for_service(
                user_message, service_functions, selected_service, context
            )

            logger.info(f"Intent analysé pour {selected_service}: {intent}")

            # Étape 4: Vérifier si confirmation nécessaire
            function_name = intent["function_name"]
            parameters = intent["parameters"]

            confirmation_required = self._requires_confirmation(function_name, parameters)

            if confirmation_required and confirmation_required.required:
                # Action nécessite confirmation - ne pas exécuter maintenant
                action_id = str(uuid.uuid4())
                self.pending_actions[action_id] = {
                    "function_name": function_name,
                    "parameters": parameters,
                    "user_message": user_message,
                    "selected_service": selected_service,
                    "created_at": datetime.now()
                }
                logger.info("voici lespending actions ",self.pending_actions)

                response = f"## ⚠️ Confirmation requise\n\n{confirmation_required.warning_message}\n\n**Action:** {function_name}\n**Paramètres:** {parameters}\n\n{confirmation_required.confirmation_text}"

                return {
                    "user_message": user_message,
                    "selected_service": selected_service,
                    "intent": intent,
                    "data": None,
                    "response": response,
                    "success": True,
                    "is_markdown": True,
                    "service_navigation": self._get_service_navigation(selected_service),
                    "confirmation_required": confirmation_required,
                    "action_id": action_id
                }

            # Étape 5: Exécuter la fonction (pas de confirmation nécessaire)
            if function_name == "general_help":
                data = await self._handle_general_help(selected_service)
            else:
                data = await self.function_registry.execute_function(function_name, parameters)

            # Étape 6: Générer une réponse naturelle
            response = self.groq_client.generate_response(data, function_name, user_message)

            return {
                "user_message": user_message,
                "selected_service": selected_service,
                "intent": intent,
                "data": data,
                "response": response,
                "success": True,
                "is_markdown": True,
                "service_navigation": self._get_service_navigation(selected_service),
                "confirmation_required": None,
                "action_id": None
            }

        except Exception as e:
            logger.error(f"Erreur traitement message: {e}")
            return {
                "user_message": user_message,
                "selected_service": "unknown",
                "intent": {"function_name": "error", "parameters": {}},
                "data": None,
                "response": f"## ❌ Erreur\n\nDésolé, j'ai rencontré une erreur lors du traitement:\n\n```\n{str(e)}\n```",
                "success": False,
                "error": str(e),
                "is_markdown": True,
                "service_navigation": None,
                "confirmation_required": None,
                "action_id": None
            }

    async def confirm_action(self, action_id: str, confirmed: bool) -> Dict:
        """Confirme ou annule une action en attente"""

        if action_id not in self.pending_actions:
            return {
                "user_message": "",
                "selected_service": "unknown",
                "intent": {"function_name": "error", "parameters": {}},
                "data": None,
                "response": "## ❌ Erreur\n\nAction introuvable ou expirée.",
                "success": False,
                "error": "Action not found",
                "is_markdown": True,
                "service_navigation": None,
                "confirmation_required": None,
                "action_id": None
            }

        pending_action = self.pending_actions[action_id]

        if not confirmed:
            # Action annulée
            del self.pending_actions[action_id]
            return {
                "user_message": pending_action["user_message"],
                "selected_service": pending_action["selected_service"],
                "intent": {"function_name": "cancelled", "parameters": {}},
                "data": None,
                "response": "## ✅ Action annulée\n\nL'action a été annulée avec succès.",
                "success": True,
                "is_markdown": True,
                "service_navigation": self._get_service_navigation(pending_action["selected_service"]),
                "confirmation_required": None,
                "action_id": None
            }

        # Action confirmée - exécuter
        try:
            function_name = pending_action["function_name"]
            parameters = pending_action["parameters"]

            # 🔥 MODIFICATION CLÉE : Passer user_confirmed=True pour les actions dangereuses
            if function_name in ["delete_entire_image", "purge_images", "cleanup_inactive_images"]:
                parameters["user_confirmed"] = True

            if function_name == "general_help":
                data = await self._handle_general_help(pending_action["selected_service"])
            else:
                data = await self.function_registry.execute_function(function_name, parameters)

            response = self.groq_client.generate_response(data, function_name, pending_action["user_message"])

            # Nettoyer l'action en attente
            del self.pending_actions[action_id]

            return {
                "user_message": pending_action["user_message"],
                "selected_service": pending_action["selected_service"],
                "intent": {"function_name": function_name, "parameters": parameters},
                "data": data,
                "response": f"## ✅ Action confirmée et exécutée\n\n{response}",
                "success": True,
                "is_markdown": True,
                "service_navigation": self._get_service_navigation(pending_action["selected_service"]),
                "confirmation_required": None,
                "action_id": None
            }

        except Exception as e:
            logger.error(f"Erreur exécution action confirmée: {e}")
            del self.pending_actions[action_id]

            return {
                "user_message": pending_action["user_message"],
                "selected_service": pending_action["selected_service"],
                "intent": {"function_name": "error", "parameters": {}},
                "data": None,
                "response": f"## ❌ Erreur lors de l'exécution\n\n```\n{str(e)}\n```",
                "success": False,
                "error": str(e),
                "is_markdown": True,
                "service_navigation": self._get_service_navigation(pending_action["selected_service"]),
                "confirmation_required": None,
                "action_id": None
            }

    async def _handle_general_help(self, selected_service: str = None) -> Dict:
        """Gère les demandes d'aide générale, optionnellement pour un service spécifique"""

        if selected_service and selected_service != "general":
            # Aide spécifique à un service
            service_info = self.function_registry.get_service_info(selected_service)
            service_functions = self.function_registry.get_functions_for_service(selected_service)

            if service_info and service_functions:
                functions_list = []
                for func_schema in service_functions:
                    functions_list.append({
                        "name": func_schema['name'],
                        "description": func_schema['description'],
                        "examples": func_schema.get('examples', [])
                    })

                return {
                    "message": f"Aide pour le service: {service_info['description']}",
                    "service_name": selected_service,
                    "service_domains": service_info.get('domains', []),
                    "available_functions": functions_list,
                    "total_functions": len(functions_list),
                    "markdown_ready": True
                }

        # Aide générale - vue d'ensemble de tous les services
        available_services = self.function_registry.get_available_services_info()
        services_summary = []

        for service_name, service_info in available_services.items():
            services_summary.append({
                "name": service_name,
                "description": service_info['description'],
                "domains": service_info.get('domains', []),
                "function_count": service_info.get('function_count', 0)
            })

        return {
            "message": "Je suis votre assistant pour la gestion des registres de conteneurs et Kubernetes.",
            "available_services": services_summary,
            "total_services": len(services_summary),
            "suggestion": "Précisez votre demande pour que je puisse vous aider plus efficacement.",
            "markdown_ready": True
        }