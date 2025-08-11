from typing import Dict, Any, List, Optional
import logging
import inspect
from app.core.decorators import CHATBOT_FUNCTIONS

logger = logging.getLogger(__name__)


class FunctionRegistry:
    def __init__(self):
        self.services = {}
        self.functions = {}
        self.services_metadata = {}

    def register_service(self, service_name: str, service_instance: Any,
                         description: str = None, domains: List[str] = None):
        """Enregistre un service avec ses métadonnées et découvre automatiquement ses fonctions chatbot"""
        self.services[service_name] = service_instance

        # Enregistrer les métadonnées du service
        self.services_metadata[service_name] = {
            'description': description or f'Service {service_name}',
            'domains': domains or ['général'],
            'functions': [],
            'function_count': 0
        }

        # Découvrir toutes les méthodes marquées avec @chatbot_function
        service_functions = []
        for attr_name in dir(service_instance):
            method = getattr(service_instance, attr_name)

            # Chercher dans le registre global
            for func_name, func_info in CHATBOT_FUNCTIONS.items():
                if (hasattr(method, '__name__') and
                        method.__name__ == func_info['function'].__name__ and
                        method.__module__ == func_info['module']):
                    # Enregistrer la fonction avec l'instance du service
                    function_entry = {
                        **func_info,
                        'service_name': service_name,
                        'service_instance': service_instance,
                        'bound_method': method
                    }

                    self.functions[func_name] = function_entry
                    service_functions.append(func_name)

                    logger.info(f"Fonction '{func_name}' enregistrée depuis le service '{service_name}'")

        # Mettre à jour les métadonnées du service
        self.services_metadata[service_name]['functions'] = service_functions
        self.services_metadata[service_name]['function_count'] = len(service_functions)

    def get_available_services_info(self) -> Dict[str, Dict]:
        """Retourne les informations des services pour la sélection"""
        return self.services_metadata

    def get_functions_for_service(self, service_name: str) -> List[Dict]:
        """Retourne les fonctions disponibles pour un service spécifique"""
        if service_name not in self.services_metadata:
            return []

        service_functions = self.services_metadata[service_name]['functions']
        schemas = []

        for func_name in service_functions:
            if func_name in self.functions:
                func_info = self.functions[func_name]
                schema = {
                    "name": func_name,
                    "description": func_info['description'],
                    "parameters": func_info['parameters_schema'],
                    "examples": func_info['examples']
                }
                schemas.append(schema)

        return schemas

    def get_available_functions(self) -> Dict[str, Dict]:
        """Retourne toutes les fonctions disponibles (pour compatibility)"""
        return self.functions

    def get_function_schemas_for_ai(self) -> List[Dict]:
        """Génère les schémas de fonctions pour l'IA Groq (deprecated - utiliser get_functions_for_service)"""
        schemas = []

        for func_name, func_info in self.functions.items():
            schema = {
                "name": func_name,
                "description": func_info['description'],
                "parameters": func_info['parameters_schema'],
                "examples": func_info['examples']
            }
            schemas.append(schema)

        return schemas

    async def execute_function(self, function_name: str, parameters: Dict[str, Any]) -> Any:
        """Exécute une fonction dynamiquement"""
        if function_name not in self.functions:
            raise ValueError(f"Fonction '{function_name}' non trouvée")

        func_info = self.functions[function_name]
        bound_method = func_info['bound_method']

        try:
            if inspect.iscoroutinefunction(bound_method):
                result = await bound_method(**parameters)
            else:
                result = bound_method(**parameters)

            return result
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution de '{function_name}': {e}")
            raise

    def get_service_by_name(self, service_name: str) -> Optional[Any]:
        """Retourne une instance de service par son nom"""
        return self.services.get(service_name)

    def list_services(self) -> List[str]:
        """Retourne la liste des noms de services enregistrés"""
        return list(self.services.keys())

    def get_service_info(self, service_name: str) -> Optional[Dict]:
        """Retourne les informations d'un service spécifique"""
        return self.services_metadata.get(service_name)