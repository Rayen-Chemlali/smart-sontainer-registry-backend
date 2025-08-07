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
            "kubernetes_service": ServiceNavigation(
                service_name="kubernetes_service",
                display_name="Kubernetes",
                dashboard_route="/dashboard/kubernetes",
                icon="server",
                description="Gérer vos pods, deployments et services"
            ),
            "registry_service": ServiceNavigation(
                service_name="registry_service",
                display_name="Container Registry",
                dashboard_route="/dashboard/registry",
                icon="package",
                description="Explorer et gérer vos images de conteneurs"
            ),
            "rules_engine": ServiceNavigation(
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
            "general": ServiceNavigation(
                service_name="general",
                display_name="Assistant IA",
                dashboard_route="/dashboard",
                icon="help-circle",
                description="Assistant IA spécialisé Smart Container Registry"
            )
        }
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

    async def _handle_general_help_system(self, user_message: str, parameters: Dict) -> Dict[str, Any]:
        """Gère les demandes d'aide générale liées au système Smart Container Registry"""

        # Analyser le type de question
        query_type = parameters.get("query_type", "system")
        topic = parameters.get("topic", "general")

        # Obtenir les informations sur tous les services disponibles
        available_services = self.function_registry.get_available_services_info()

        help_data = {
            "assistant_role": "Assistant IA spécialisé Smart Container Registry",
            "project_description": "Solution intelligente pour optimiser la gestion et réduire les coûts de stockage des images de conteneurs",
            "main_features": [
                "Chatbot IA conversationnel avec validation obligatoire",
                "Dashboard unifié Kubernetes + AWS S3",
                "Système de rapports administrateur temps réel",
                "Sécurité renforcée avec RBAC et soft delete"
            ],
            "available_services": [],
            "capabilities": [
                "Analyse et gestion des images de conteneurs",
                "Supervision des déploiements Kubernetes",
                "Configuration de règles automatiques de nettoyage",
                "Rapports et métriques en temps réel",
                "Validation sécurisée des actions critiques"
            ],
            "example_commands": [
                "Montre-moi l'état des pods Kubernetes",
                "Liste les images non utilisées depuis 30 jours",
                "Configure une règle de nettoyage automatique",
                "Affiche la vue d'ensemble de l'infrastructure",
                "Supprime les images obsolètes (avec confirmation)"
            ],
            "help_topics": {
                "kubernetes": "Gestion des pods, deployments, services et ressources K8s",
                "registry": "Exploration, analyse et nettoyage des images de conteneurs",
                "rules": "Configuration des règles automatiques et lifecycle policies",
                "security": "Validation, backup automatique et contrôle d'accès",
                "monitoring": "Métriques, logs et rapports administrateur"
            },
            "user_query": user_message,
            "query_classification": query_type
        }

        # Construire la liste des services disponibles avec détails
        for service_name, service_info in available_services.items():
            if service_name != "general":  # Exclure le service general de la liste
                service_detail = {
                    "name": service_name,
                    "display_name": service_info.get("display_name", service_name.title()),
                    "description": service_info.get("description", ""),
                    "domains": service_info.get("domains", []),
                    "function_count": service_info.get("function_count", 0),
                    "icon": self._get_service_icon(service_name)
                }
                help_data["available_services"].append(service_detail)

        # Ajouter des conseils spécifiques selon le contexte
        help_data["contextual_tips"] = self._get_contextual_tips(topic, user_message)

        return help_data

    async def _handle_general_help_off_topic(self, user_message: str, parameters: Dict) -> Dict[str, Any]:
        """Gère les demandes hors contexte (non liées au projet)"""

        topic = parameters.get("topic", "unknown")

        return {
            "response_type": "off_topic",
            "user_query": user_message,
            "topic_detected": topic,
            "message": "Désolé, je suis spécialisé dans la gestion du Smart Container Registry",
            "redirection": "Je peux vous aider avec la gestion des conteneurs, Kubernetes, et l'optimisation des coûts de stockage",
            "available_help": [
                "Gestion des images de conteneurs",
                "Supervision Kubernetes",
                "Configuration des règles automatiques",
                "Analyse des coûts de stockage",
                "Rapports et métriques système"
            ],
            "suggested_questions": [
                "Comment puis-je optimiser mes coûts de stockage ?",
                "Montre-moi l'état de mes pods Kubernetes",
                "Comment configurer le nettoyage automatique ?",
                "Quelles sont les fonctionnalités disponibles ?"
            ]
        }

    def _get_service_icon(self, service_name: str) -> str:
        """Retourne l'icône appropriée pour un service"""
        icons = {
            "kubernetes_service": "server",
            "registry_service": "package",
            "rules_engine": "settings",
            "overview": "layout-dashboard"
        }
        return icons.get(service_name, "tool")

    def _get_contextual_tips(self, topic: str, user_message: str) -> list[str]:
        """Retourne des conseils contextuels selon le sujet"""

        # Analyser les mots-clés dans le message
        message_lower = user_message.lower()

        if any(keyword in message_lower for keyword in ['coût', 'prix', 'économie', 'optimiser']):
            return [
                "Le Smart Container Registry peut réduire drastiquement vos coûts de stockage",
                "Configurez des règles automatiques pour nettoyer les images obsolètes",
                "Utilisez les rapports pour identifier les images non utilisées",
                "Le système de backup automatique protège vos données critiques"
            ]
        elif any(keyword in message_lower for keyword in ['sécurité', 'sûr', 'risque']):
            return [
                "Toutes les actions critiques nécessitent une validation explicite",
                "Le système RBAC contrôle finement les accès",
                "Le soft delete permet un rollback pendant 30 jours",
                "Les métadonnées sensibles sont chiffrées"
            ]
        elif any(keyword in message_lower for keyword in ['kubernetes', 'k8s', 'pod', 'deployment']):
            return [
                "Supervisez vos déploiements K8s en temps réel",
                "Analysez l'utilisation des images dans vos clusters",
                "Configurez des alertes pour les ressources critiques",
                "Gérez les replicas et la scalabilité facilement"
            ]
        elif any(keyword in message_lower for keyword in ['image', 'docker', 'container', 'registry']):
            return [
                "Explorez vos registries S3 avec une interface unifiée",
                "Identifiez les images orphelines et obsolètes",
                "Configurez des lifecycle policies personnalisées",
                "Suivez les métriques d'usage en temps réel"
            ]
        else:
            return [
                "Explorez les 4 services principaux via le dashboard",
                "Utilisez des commandes en langage naturel",
                "Toutes les actions critiques sont sécurisées et validées",
                "Consultez les rapports pour une vue d'ensemble complète"
            ]

    async def _handle_general_help(self, selected_service: str, user_message: str = "", parameters: Dict = None) -> \
    Dict[str, Any]:
        """Gère les demandes d'aide générale - Point d'entrée unifié"""

        if parameters is None:
            parameters = {}

        # Déterminer le type de demande d'aide
        query_type = parameters.get("query_type", "system")

        if query_type == "off_topic":
            return await self._handle_general_help_off_topic(user_message, parameters)
        else:
            return await self._handle_general_help_system(user_message, parameters)

    def _get_service_tips(self, service_name: str) -> list[str]:
        """Retourne des conseils spécifiques au service"""
        tips_mapping = {
            "kubernetes_service": [
                "Utilisez 'kubectl get pods' pour voir l'état de vos pods",
                "Les deployments permettent de gérer facilement les replicas",
                "Surveillez les ressources avec 'kubectl top'",
                "Utilisez les namespaces pour organiser vos applications"
            ],
            "registry_service": [
                "Nettoyez régulièrement les images inutilisées",
                "Utilisez des tags sémantiques pour vos images",
                "Vérifiez la sécurité de vos images régulièrement",
                "Optimisez la taille de vos images Docker"
            ],
            "rules_engine": [
                "Testez vos règles sur un environnement de test d'abord",
                "Documentez vos règles pour faciliter la maintenance",
                "Utilisez des conditions précises pour éviter les faux positifs",
                "Surveillez les logs des règles automatiques"
            ],
            "overview": [
                "Consultez régulièrement les métriques système",
                "Configurez des alertes pour les ressources critiques",
                "Maintenez un équilibre entre performance et coût",
                "Planifiez la maintenance pendant les heures creuses"
            ],
            "general": [
                "Explorez les services disponibles : Kubernetes, Registry, Rules Engine",
                "Utilisez des commandes précises pour de meilleurs résultats",
                "Demandez de l'aide spécifique pour chaque service",
                "N'hésitez pas à poser des questions sur votre infrastructure"
            ]
        }

        return tips_mapping.get(service_name, [
            "Explorez les différentes fonctionnalités disponibles",
            "N'hésitez pas à demander de l'aide spécifique",
            "Vérifiez régulièrement l'état de vos services"
        ])

    def _get_function_help(self, function_name: str) -> Dict[str, Any]:
        """Retourne l'aide détaillée pour une fonction spécifique"""

        function_info = self.function_registry.get_function_info(function_name)

        if not function_info:
            return {
                "error": f"Fonction '{function_name}' introuvable",
                "available_functions": list(self.function_registry.get_all_function_names())
            }

        return {
            "function_name": function_name,
            "description": function_info.get("description", ""),
            "parameters": function_info.get("parameters", {}),
            "examples": function_info.get("examples", []),
            "service": function_info.get("service", ""),
            "requires_confirmation": any(keyword in function_name.lower()
                                         for keyword in ['delete', 'remove', 'purge', 'cleanup', 'scale', 'restart']),
            "usage_notes": function_info.get("usage_notes", [])
        }

    def _format_parameters_for_display(self, parameters: Dict) -> str:
        """Formate les paramètres pour l'affichage en Markdown"""
        if not parameters:
            return "- *Aucun paramètre*"

        formatted_params = []
        for key, value in parameters.items():
            if isinstance(value, (dict, list)):
                formatted_params.append(f"- **{key}:** `{str(value)}`")
            else:
                formatted_params.append(f"- **{key}:** `{value}`")

        return "\n".join(formatted_params)

    def _clean_expired_actions(self) -> None:
        """Nettoie les actions expirées (plus de 10 minutes)"""
        current_time = datetime.now()
        expired_actions = []

        for action_id, action_data in self.pending_actions.items():
            if (current_time - action_data["created_at"]).total_seconds() > 600:  # 10 minutes
                expired_actions.append(action_id)

        for action_id in expired_actions:
            del self.pending_actions[action_id]
            logger.info(f"Action expirée supprimée: {action_id}")

    def get_pending_actions_count(self) -> int:
        """Retourne le nombre d'actions en attente"""
        self._clean_expired_actions()
        return len(self.pending_actions)

    def get_system_status(self) -> Dict[str, Any]:
        """Retourne le statut du système chatbot"""
        return {
            "pending_actions": self.get_pending_actions_count(),
            "available_services": len(self.function_registry.get_available_services_info()),
            "total_functions": len(self.function_registry.get_all_function_names()),
            "system_health": "operational",
            "last_cleanup": datetime.now().isoformat()
        }

    async def process_message(self, user_message: str, context: Optional[Dict] = None) -> Dict:
        """Traite un message utilisateur avec sélection de service optimisée et post-traitement Markdown"""

        # Nettoyer les actions expirées
        self._clean_expired_actions()

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
                logger.info("Pending actions:", self.pending_actions)

                # 🔥 POST-TRAITEMENT pour les confirmations
                confirmation_response = f"""## ⚠️ Confirmation requise

{confirmation_required.warning_message}

**Action demandée:** `{function_name}`

**Paramètres:**
{self._format_parameters_for_display(parameters)}

{confirmation_required.confirmation_text}"""

                # Post-traiter la réponse de confirmation
                formatted_response = self.groq_client.format_response_for_frontend(
                    confirmation_response, function_name, parameters
                )

                return {
                    "user_message": user_message,
                    "selected_service": selected_service,
                    "intent": intent,
                    "data": None,
                    "response": formatted_response,
                    "success": True,
                    "is_markdown": True,
                    "service_navigation": self._get_service_navigation(selected_service),
                    "confirmation_required": confirmation_required,
                    "action_id": action_id
                }

            # Étape 5: Exécuter la fonction (pas de confirmation nécessaire)
            # 🔥 GESTION SPÉCIALISÉE pour les fonctions general_help
            if function_name in ["general_help", "general_help_system", "general_help_off_topic"]:
                data = await self._handle_general_help(selected_service, user_message, parameters)
            else:
                data = await self.function_registry.execute_function(function_name, parameters)

            # Étape 6: Générer une réponse naturelle avec post-traitement Markdown
            response = self.groq_client.generate_response_with_formatting(
                data, function_name, user_message
            )

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

            # 🔥 POST-TRAITEMENT pour les erreurs aussi
            error_response = f"""## ❌ Erreur système

Une erreur inattendue s'est produite lors du traitement de votre demande.

**Détails techniques:**
```
{str(e)}
```

**Suggestion:** Veuillez réessayer ou reformuler votre demande."""

            formatted_error = self.groq_client.format_response_for_frontend(
                error_response, "error", {"error": str(e)}
            )

            return {
                "user_message": user_message,
                "selected_service": "unknown",
                "intent": {"function_name": "error", "parameters": {}},
                "data": None,
                "response": formatted_error,
                "success": False,
                "error": str(e),
                "is_markdown": True,
                "service_navigation": None,
                "confirmation_required": None,
                "action_id": None
            }

    async def confirm_action(self, action_id: str, confirmed: bool) -> Dict:
        """Confirme ou annule une action en attente avec post-traitement Markdown"""

        if action_id not in self.pending_actions:
            error_response = """## ❌ Action introuvable

L'action demandée est introuvable ou a expiré.

**Causes possibles:**
- Action déjà traitée
- Session expirée  
- Identifiant invalide

**Solution:** Veuillez relancer votre demande."""

            formatted_error = self.groq_client.format_response_for_frontend(
                error_response, "error", {"error": "Action not found"}
            )

            return {
                "user_message": "",
                "selected_service": "unknown",
                "intent": {"function_name": "error", "parameters": {}},
                "data": None,
                "response": formatted_error,
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

            cancelled_response = """## ✅ Action annulée

L'opération a été annulée avec succès.

Aucune modification n'a été apportée à votre système."""

            formatted_cancelled = self.groq_client.format_response_for_frontend(
                cancelled_response, "cancelled", {}
            )

            return {
                "user_message": pending_action["user_message"],
                "selected_service": pending_action["selected_service"],
                "intent": {"function_name": "cancelled", "parameters": {}},
                "data": None,
                "response": formatted_cancelled,
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

            if function_name in ["general_help", "general_help_system", "general_help_off_topic"]:
                data = await self._handle_general_help(pending_action["selected_service"],
                                                       pending_action["user_message"], parameters)
            else:
                data = await self.function_registry.execute_function(function_name, parameters)

            # 🔥 POST-TRAITEMENT avec préfixe de confirmation
            initial_response = self.groq_client.generate_response(data, function_name, pending_action["user_message"])

            confirmed_response = f"""## ✅ Action confirmée et exécutée

{initial_response}"""

            final_response = self.groq_client.format_response_for_frontend(
                confirmed_response, function_name, data
            )

            # Nettoyer l'action en attente
            del self.pending_actions[action_id]

            return {
                "user_message": pending_action["user_message"],
                "selected_service": pending_action["selected_service"],
                "intent": {"function_name": function_name, "parameters": parameters},
                "data": data,
                "response": final_response,
                "success": True,
                "is_markdown": True,
                "service_navigation": self._get_service_navigation(pending_action["selected_service"]),
                "confirmation_required": None,
                "action_id": None
            }

        except Exception as e:
            logger.error(f"Erreur exécution action confirmée: {e}")
            del self.pending_actions[action_id]

            execution_error = f"""## ❌ Erreur lors de l'exécution

L'action a été confirmée mais son exécution a échoué.

**Erreur technique:**
```
{str(e)}
```

**Action demandée:** `{pending_action["function_name"]}`

**Suggestion:** Vérifiez les paramètres et réessayez."""

            formatted_execution_error = self.groq_client.format_response_for_frontend(
                execution_error, "error", {"error": str(e)}
            )

            return {
                "user_message": pending_action["user_message"],
                "selected_service": pending_action["selected_service"],
                "intent": {"function_name": "error", "parameters": {}},
                "data": None,
                "response": formatted_execution_error,
                "success": False,
                "error": str(e),
                "is_markdown": True,
                "service_navigation": self._get_service_navigation(pending_action["selected_service"]),
                "confirmation_required": None,
                "action_id": None
            }