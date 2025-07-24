from typing import Dict, Any, Optional, List
import inspect
from functools import wraps

# Registre global des fonctions
CHATBOT_FUNCTIONS = {}


def chatbot_function(
        name: str,
        description: str,
        parameters_schema: Optional[Dict] = None,
        examples: Optional[List[str]] = None
):
    """Décorateur pour enregistrer automatiquement une fonction comme disponible pour le chatbot"""

    def decorator(func):
        # Extraire automatiquement les paramètres de la fonction
        sig = inspect.signature(func)
        auto_parameters = {}

        for param_name, param in sig.parameters.items():
            if param_name != 'self':  # Ignorer self pour les méthodes
                auto_parameters[param_name] = {
                    "type": str(param.annotation) if param.annotation != param.empty else "Any",
                    "required": param.default == param.empty,
                    "default": param.default if param.default != param.empty else None
                }

        # Enregistrer la fonction
        CHATBOT_FUNCTIONS[name] = {
            "function": func,
            "description": description,
            "parameters_schema": parameters_schema or auto_parameters,
            "examples": examples or [],
            "module": func.__module__,
            "class": None
        }

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator