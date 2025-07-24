from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.external.groq_client import GroqClient
from app.core.function_registry import FunctionRegistry
import logging

logger = logging.getLogger(__name__)


class ChatbotService:
    def __init__(self, groq_client: GroqClient, function_registry: FunctionRegistry):
        self.groq_client = groq_client
        self.function_registry = function_registry

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

            # Étape 4: Exécuter la fonction appropriée
            function_name = intent["function_name"]
            parameters = intent["parameters"]

            # Fonction d'aide générale si aucune fonction trouvée
            if function_name == "general_help":
                data = await self._handle_general_help(selected_service)
            else:
                data = await self.function_registry.execute_function(function_name, parameters)

            # Étape 5: Générer une réponse naturelle
            response = self.groq_client.generate_response(data, function_name, user_message)

            return {
                "user_message": user_message,
                "selected_service": selected_service,
                "intent": intent,
                "data": data,
                "response": response,
                "success": True,
                "is_markdown": True
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
                "is_markdown": True
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

    async def process_message_with_service_hint(
            self,
            user_message: str,
            preferred_service: str = None,
            context: Optional[Dict] = None
    ) -> Dict:
        """Version alternative qui permet de forcer un service spécifique"""

        if preferred_service and preferred_service in self.function_registry.list_services():
            # Utiliser directement le service spécifié
            service_functions = self.function_registry.get_functions_for_service(preferred_service)

            intent = self.groq_client.analyze_user_intent_for_service(
                user_message, service_functions, preferred_service, context
            )

            logger.info(f"Intent analysé pour service forcé {preferred_service}: {intent}")

            try:
                function_name = intent["function_name"]
                parameters = intent["parameters"]

                if function_name == "general_help":
                    data = await self._handle_general_help(preferred_service)
                else:
                    data = await self.function_registry.execute_function(function_name, parameters)

                response = self.groq_client.generate_response(data, function_name, user_message)

                return {
                    "user_message": user_message,
                    "selected_service": preferred_service,
                    "intent": intent,
                    "data": data,
                    "response": response,
                    "success": True,
                    "is_markdown": True,
                    "forced_service": True
                }

            except Exception as e:
                logger.error(f"Erreur service forcé {preferred_service}: {e}")
                return {
                    "user_message": user_message,
                    "selected_service": preferred_service,
                    "intent": intent,
                    "data": None,
                    "response": f"## ❌ Erreur dans {preferred_service}\n\n```\n{str(e)}\n```",
                    "success": False,
                    "error": str(e),
                    "is_markdown": True,
                    "forced_service": True
                }

        # Retomber sur le processus normal si le service forcé n'existe pas
        return await self.process_message(user_message, context)