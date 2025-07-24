from groq import Groq
import logging
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"

    def select_best_service(self, user_message: str, available_services: Dict[str, Dict]) -> str:
        """Première étape: Sélectionner le meilleur service basé sur l'intention"""

        services_description = self._build_services_description(available_services)

        system_prompt = f"""Tu es un assistant intelligent pour la gestion des registres de conteneurs et Kubernetes.
        Tu dois analyser la demande utilisateur et choisir le SERVICE le plus approprié.

        SERVICES DISPONIBLES:
        {services_description}

        Réponds UNIQUEMENT avec un JSON valide au format:
        {{
            "service_name": "nom_du_service",
            "confidence": 0.95,
            "reasoning": "explication courte"
        }}

        Si aucun service ne correspond clairement, choisis "general" avec une faible confidence.
        """

        user_prompt = f'Demande utilisateur: "{user_message}"'

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=256,  # Paramètre correct pour Groq
                top_p=0.9,
                stream=False,
                stop=None,
            )

            response_text = completion.choices[0].message.content.strip()

            # Nettoyer le JSON
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()

            try:
                parsed_response = json.loads(response_text)
                return parsed_response.get("service_name", "general")
            except json.JSONDecodeError:
                logger.error(f"Erreur JSON parsing service selection: {response_text}")
                return "general"

        except Exception as e:
            logger.error(f"Erreur Groq API service selection: {e}")
            return "general"

    def analyze_user_intent_for_service(
            self,
            user_message: str,
            service_functions: List[Dict],
            service_name: str,
            context: Optional[Dict] = None
    ) -> Dict:
        """Deuxième étape: Analyser l'intention pour les fonctions du service sélectionné"""

        if not service_functions:
            return {
                "function_name": "general_help",
                "parameters": {},
                "confidence": 0.1,
                "reasoning": f"Aucune fonction disponible pour le service {service_name}"
            }

        functions_description = self._build_functions_description(service_functions)

        system_prompt = f"""Tu es un assistant spécialisé dans le service: {service_name}
        Tu dois analyser les demandes des utilisateurs et déterminer quelle fonction appeler.

        FONCTIONS DISPONIBLES POUR CE SERVICE:
        {functions_description}

        Réponds UNIQUEMENT avec un JSON valide au format:
        {{
            "function_name": "nom_de_la_fonction",
            "parameters": {{
                "param1": "valeur1",
                "param2": "valeur2"
            }},
            "confidence": 0.95,
            "reasoning": "explication courte"
        }}

        Si aucune fonction ne correspond, utilise:
        {{
            "function_name": "general_help",
            "parameters": {{}},
            "confidence": 0.1,
            "reasoning": "Aucune fonction correspondante dans ce service"
        }}
        """

        user_prompt = f"""
        Demande de l'utilisateur: "{user_message}"
        Service sélectionné: {service_name}
        Context additionnel: {json.dumps(context) if context else "Aucun"}

        Analyse cette demande et détermine quelle fonction appeler avec quels paramètres.
        """

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=512,  # Paramètre correct pour Groq
                top_p=0.9,
                stream=False,
                stop=None,
            )

            response_text = completion.choices[0].message.content.strip()
            logger.info(f"Groq response for service {service_name}: {response_text}")

            # Nettoyer le JSON
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()

            try:
                parsed_response = json.loads(response_text)
                return parsed_response
            except json.JSONDecodeError:
                logger.error(f"Erreur JSON parsing: {response_text}")
                return {
                    "function_name": "general_help",
                    "parameters": {},
                    "confidence": 0.1,
                    "reasoning": "Erreur de parsing de la réponse"
                }

        except Exception as e:
            logger.error(f"Erreur Groq API: {e}")
            return {
                "function_name": "general_help",
                "parameters": {},
                "confidence": 0.1,
                "reasoning": f"Erreur API: {str(e)}"
            }

    def _build_services_description(self, services: Dict[str, Dict]) -> str:
        """Construit la description des services disponibles"""
        descriptions = []

        for service_name, service_info in services.items():
            description = f"""
{service_name}: {service_info.get('description', 'Service pour la gestion système')}
  Domaines: {', '.join(service_info.get('domains', ['général']))}
  Fonctions disponibles: {service_info.get('function_count', 0)}
"""
            descriptions.append(description)

        return "\n".join(descriptions)

    def _build_functions_description(self, functions: List[Dict]) -> str:
        """Construit la description des fonctions pour l'IA"""
        descriptions = []

        for func in functions:
            params_desc = []
            if func.get('parameters'):
                for param_name, param_info in func['parameters'].items():
                    required = "(requis)" if param_info.get('required', False) else "(optionnel)"
                    default = f", défaut: {param_info.get('default')}" if param_info.get('default') else ""
                    params_desc.append(f"  - {param_name} {required}{default}: {param_info.get('description', '')}")

            examples_desc = ""
            if func.get('examples'):
                examples_desc = f"\n  Exemples: {', '.join(func['examples'])}"

            description = f"""
{func['name']}: {func['description']}
  Paramètres:
{chr(10).join(params_desc) if params_desc else "    Aucun paramètre"}{examples_desc}
"""
            descriptions.append(description)

        return "\n".join(descriptions)

    def generate_response(self, data: Any, function_name: str, user_message: str) -> str:
        """Génère une réponse naturelle basée sur les données"""
        system_prompt = """Tu es un assistant spécialisé dans la gestion des registres de conteneurs et Kubernetes.
        Tu dois présenter les données techniques de manière claire et conversationnelle en français.

        FORMATAGE MARKDOWN SIMPLE:
        - Utilise # pour le titre principal SEULEMENT
        - Utilise ## pour les sections importantes
        - Utilise des listes simples avec - 
        - Utilise `code` pour les noms techniques (pas de blocs de code)
        - Utilise **gras** pour les éléments importants
        - Évite les tableaux complexes, préfère les listes
        - Pas de > pour les citations
        - Pas de blocs de code ```

        Sois précis, concis et utile. Structure simple et lisible.
        """

        user_prompt = f"""
        Fonction exécutée: {function_name}
        Demande originale: "{user_message}"

        Données récupérées:
        {json.dumps(data, indent=2, ensure_ascii=False)}

        Présente ces données de manière claire et conversationnelle en format Markdown SIMPLE.
        Si les données sont vides ou contiennent des erreurs, explique la situation.
        Utilise des listes simples pour les données, évite les tableaux complexes.
        """

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1024,  # Paramètre correct pour Groq
                top_p=0.9,
                stream=False,
                stop=None,
            )

            raw_response = completion.choices[0].message.content

            # Formatage simple et direct
            formatted_response = self._ensure_simple_markdown(raw_response)

            return formatted_response

        except Exception as e:
            logger.error(f"Erreur génération réponse: {e}")
            return f"# Erreur\n\nDésolé, j'ai rencontré une erreur lors de la génération de la réponse: `{str(e)}`"

    def _ensure_simple_markdown(self, response: str) -> str:
        """Assure un formatage Markdown simple et propre"""
        # Nettoyage basique
        response = response.strip()

        # Éviter les blocs de code complexes
        response = response.replace('```json', '`json`')
        response = response.replace('```yaml', '`yaml`')
        response = response.replace('```', '`')

        # Simplifier les titres multiples
        response = response.replace('####', '##')
        response = response.replace('###', '##')

        # Éviter les lignes vides multiples
        while '\n\n\n' in response:
            response = response.replace('\n\n\n', '\n\n')

        # S'assurer qu'il y a un titre principal
        if not response.startswith('#'):
            response = f"# Résultats\n\n{response}"

        return response