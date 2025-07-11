from groq import Groq
import logging
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"

    def analyze_user_intent(self, user_message: str, context: Optional[Dict] = None) -> Dict:
        """Analyse l'intention de l'utilisateur et détermine quelle action effectuer"""

        system_prompt = """Tu es un assistant intelligent spécialisé dans la gestion des registres de conteneurs et Kubernetes.
        Tu dois analyser les demandes des utilisateurs et déterminer quelle action effectuer.

        Actions disponibles:
        1. "list_images" - Lister les images du registre
        2. "list_pods" - Lister les pods Kubernetes
        3. "list_deployments" - Lister les deployments
        4. "list_namespaces" - Lister les namespaces
        5. "get_overview" - Obtenir une vue d'ensemble
        6. "get_deployed_images" - Obtenir les images déployées
        7. "get_s3_buckets" - Lister les buckets S3
        8. "get_image_details" - Obtenir les détails d'une image spécifique
        9. "compare_registry_deployment" - Comparer registre et déploiement
        10. "general_info" - Informations générales ou aide

        Paramètres possibles:
        - namespace: nom du namespace (optionnel)
        - image_name: nom de l'image (optionnel)
        - bucket_name: nom du bucket (optionnel)

        Réponds UNIQUEMENT avec un JSON valide au format:
        {
            "action": "nom_action",
            "parameters": {
                "namespace": "valeur_optionnelle",
                "image_name": "valeur_optionnelle",
                "bucket_name": "valeur_optionnelle"
            },
            "confidence": 0.95,
            "reasoning": "explication courte"
        }

        Exemples de demandes et réponses:
        - "liste-moi toutes les images" -> {"action": "list_images", "parameters": {}, "confidence": 0.9, "reasoning": "Demande claire de listing des images"}
        - "montre-moi les pods du namespace production" -> {"action": "list_pods", "parameters": {"namespace": "production"}, "confidence": 0.95, "reasoning": "Demande spécifique de pods avec namespace"}
        - "quelles images sont déployées?" -> {"action": "get_deployed_images", "parameters": {}, "confidence": 0.9, "reasoning": "Demande des images actuellement déployées"}
        """

        user_prompt = f"""
        Demande de l'utilisateur: "{user_message}"

        Context additionnel: {json.dumps(context) if context else "Aucun"}

        Analyse cette demande et réponds avec le JSON approprié.
        """

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_completion_tokens=512,
                top_p=0.9,
                stream=False,
                stop=None,
            )

            response_text = completion.choices[0].message.content
            logger.info(f"Groq response: {response_text}")

            # Nettoyer et parser le JSON
            response_text = response_text.strip()
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
                    "action": "general_info",
                    "parameters": {},
                    "confidence": 0.5,
                    "reasoning": "Erreur de parsing de la réponse"
                }

        except Exception as e:
            logger.error(f"Erreur Groq API: {e}")
            return {
                "action": "general_info",
                "parameters": {},
                "confidence": 0.1,
                "reasoning": f"Erreur API: {str(e)}"
            }

    def generate_response(self, data: Any, action: str, user_message: str) -> str:
        """Génère une réponse naturelle basée sur les données"""

        system_prompt = """Tu es un assistant spécialisé dans la gestion des registres de conteneurs et Kubernetes.
        Tu dois présenter les données techniques de manière claire et conversationnelle en français.

        Sois précis, concis et utile. Utilise un ton professionnel mais accessible.
        Structure ta réponse de manière logique avec des puces ou des listes quand approprié.
        """

        user_prompt = f"""
        Action effectuée: {action}
        Demande originale: "{user_message}"

        Données récupérées:
        {json.dumps(data, indent=2, ensure_ascii=False)}

        Présente ces données de manière claire et conversationnelle. 
        Si les données sont vides ou contiennent des erreurs, explique la situation.
        """

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_completion_tokens=1024,
                top_p=0.9,
                stream=False,
                stop=None,
            )

            return completion.choices[0].message.content

        except Exception as e:
            logger.error(f"Erreur génération réponse: {e}")
            return f"Désolé, j'ai rencontré une erreur lors de la génération de la réponse: {str(e)}"


