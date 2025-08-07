from groq import Groq
import logging
from typing import Dict, List, Optional, Any
import json
import re

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

        RÈGLES SPÉCIALES POUR LE SERVICE "general":
        - Utilise "general" SEULEMENT pour:
          * Questions d'aide sur le système Smart Container Registry
          * Questions techniques sur Docker, S3, Container Registry, Kubernetes dans le contexte du projet
          * Demandes de navigation ou d'explication des fonctionnalités disponibles
          * Questions "Comment tu peux m'aider ?" ou "Que peux-tu faire ?"

        - NE PAS utiliser "general" pour:
          * Demandes de code non liées au projet (Python, Java, etc.)
          * Questions hors contexte (météo, actualités, etc.)
          * Demandes d'aide sur des technologies non utilisées dans le projet

        Réponds UNIQUEMENT avec un JSON valide au format:
        {{
            "service_name": "nom_du_service",
            "confidence": 0.95,
            "reasoning": "explication courte"
        }}

        Si aucun service ne correspond clairement, choisis "general" SEULEMENT si c'est lié au contexte du projet.
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
                max_tokens=256,
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

        # Prompt spécialisé pour le service general
        if service_name == "general":
            system_prompt = f"""Tu es l'assistant IA du Smart Container Registry, spécialisé dans la gestion intelligente des images de conteneurs et Kubernetes.

            CONTEXTE DU PROJET:
            - Smart Container Registry : Solution IA pour optimiser les coûts de stockage des images
            - Chatbot conversationnel avec validation obligatoire pour les actions critiques
            - Gestion unifiée Kubernetes + AWS S3 avec rapports temps réel
            - Sécurité renforcée : RBAC, soft delete, backup automatique

            SERVICES DISPONIBLES DANS LE SYSTÈME:
            - kubernetes_service : Gestion des pods, deployments, services K8s
            - registry_service : Exploration et gestion des images de conteneurs
            - rules_engine : Configuration des règles automatiques de suppression
            - overview : Vue d'ensemble de l'infrastructure

            ANALYSE DE LA DEMANDE:
            Si la demande est:
            1. **LIÉE AU PROJET** (aide système, questions Docker/S3/K8s, navigation) → utilise "general_help_system"
            2. **HORS CONTEXTE** (code Python, sujets non liés) → utilise "general_help_off_topic"

            FONCTIONS DISPONIBLES:
            {functions_description}

            Réponds UNIQUEMENT avec un JSON valide au format:
            {{
                "function_name": "nom_de_la_fonction",
                "parameters": {{
                    "query_type": "system|off_topic",
                    "topic": "sujet_principal"
                }},
                "confidence": 0.95,
                "reasoning": "explication courte"
            }}
            """
        else:
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
                max_tokens=512,
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

    def generate_response(self, data: Any, function_name: str, user_message: str) -> str:
        """Génère une réponse naturelle basée sur les données (version de base)"""
        system_prompt = """Tu es un assistant technique spécialisé du Smart Container Registry. 
        Présente les informations de manière claire et structurée.
        Focus sur les données importantes, évite les détails superflus.
        Utilise un français professionnel mais accessible."""

        user_prompt = f"""
        Fonction: {function_name}
        Demande: "{user_message}"
        Données: {json.dumps(data, indent=2, ensure_ascii=False)}

        Présente ces informations de manière claire et utile.
        """

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800,
                top_p=0.9,
                stream=False,
                stop=None,
            )

            return completion.choices[0].message.content

        except Exception as e:
            logger.error(f"Erreur génération réponse: {e}")
            return f"# Erreur\n\nDésolé, j'ai rencontré une erreur lors de la génération de la réponse: `{str(e)}`"

    def generate_response_with_formatting(self, data: Any, function_name: str, user_message: str) -> str:
        """Génère une réponse avec post-traitement Markdown optimisé"""

        # Génération de la réponse initiale
        raw_response = self.generate_response(data, function_name, user_message)

        # Post-traitement pour le frontend
        formatted_response = self.format_response_for_frontend(raw_response, function_name, data)

        return formatted_response

    def format_response_for_frontend(self, raw_response: str, function_name: str, data: Any) -> str:
        """Post-traite la réponse pour un rendu Markdown optimisé côté frontend"""

        system_prompt = """Tu es un expert en formatage Markdown pour interfaces web modernes du Smart Container Registry.

        Tu dois prendre une réponse technique et la reformater pour un rendu parfait en Markdown avec ces RÈGLES STRICTES:

        STRUCTURE MARKDOWN REQUISE:
        - UN SEUL titre principal avec # (ou ## si c'est un sous-élément)
        - Sections avec ## (maximum 2-3 sections)
        - Sous-sections avec ### si nécessaire
        - Listes avec - pour les éléments simples
        - Listes numérotées 1. 2. 3. pour les étapes
        - `code inline` pour les noms techniques, commandes, valeurs
        - **gras** pour les informations importantes
        - **NE JAMAIS** utiliser de tableaux HTML ou complexes
        - **NE JAMAIS** utiliser de > citations

        FORMATAGE SPÉCIAL (très important):
        - Pour les erreurs: ## ❌ [Titre]
        - Pour les succès: ## ✅ [Titre] 
        - Pour les avertissements: ## ⚠️ [Titre]
        - Pour les informations: ## ℹ️ [Titre]

        PRÉSENTATION DES DONNÉES:
        - Transformer les données techniques en listes lisibles
        - Regrouper les informations similaires
        - Utiliser des sous-sections pour organiser
        - Mettre en évidence les valeurs importantes avec `backticks`
        - Ajouter des émojis appropriés pour la lisibilité (mais modérément)

        STYLE CONVERSATIONNEL:
        - Utiliser un ton professionnel mais accessible
        - Expliquer brièvement les termes techniques
        - Structurer l'information du général au spécifique
        - Terminer par une suggestion d'action si appropriée
        - Éviter les répétitions
        """

        user_prompt = f"""
        FONCTION EXÉCUTÉE: {function_name}

        RÉPONSE BRUTE À REFORMATER:
        {raw_response}

        DONNÉES ORIGINALES:
        {json.dumps(data, indent=2, ensure_ascii=False) if data else "Aucune donnée"}

        Reformate cette réponse en Markdown parfaitement structuré pour un affichage web moderne.
        Assure-toi que chaque élément soit clairement organisé et facile à lire.
        Utilise les indicateurs de statut appropriés (✅❌⚠️ℹ️) selon le contexte.
        """

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # Plus créatif pour le formatage
                max_tokens=1200,
                top_p=0.9,
                stream=False,
                stop=None,
            )

            formatted_response = completion.choices[0].message.content.strip()

            # Post-traitement pour assurer la cohérence
            formatted_response = self._ensure_markdown_consistency(formatted_response)

            return formatted_response

        except Exception as e:
            logger.error(f"Erreur formatage Markdown: {e}")
            # Fallback avec formatage basique
            return self._basic_markdown_format(raw_response)

    def _ensure_markdown_consistency(self, content: str) -> str:
        """Assure la cohérence du formatage Markdown"""

        # Nettoyer les espaces multiples
        content = re.sub(r' +', ' ', content)

        # Assurer un seul titre principal (garder seulement le premier #)
        titles = re.findall(r'^# (.+)$', content, re.MULTILINE)
        if len(titles) > 1:
            # Convertir les titres supplémentaires en sections
            content = re.sub(r'^# (.+)$', r'## \1', content, flags=re.MULTILINE)
            # Remettre le premier comme titre principal
            content = re.sub(r'^## (.+)$', r'# \1', content, count=1, flags=re.MULTILINE)

        # Assurer des espaces corrects autour des sections
        content = re.sub(r'\n(#{1,3} .+)\n', r'\n\n\1\n\n', content)

        # Nettoyer les listes mal formatées
        content = re.sub(r'\n- ', r'\n\n- ', content)
        content = re.sub(r'\n\n\n- ', r'\n\n- ', content)

        # Espacement autour des blocs spéciaux
        content = re.sub(r'\n(## [❌✅⚠️ℹ️])', r'\n\n\1', content)

        # Nettoyer les sauts de ligne multiples
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Assurer que les blocs de code sont bien séparés
        content = re.sub(r'([^\n])\n```', r'\1\n\n```', content)
        content = re.sub(r'```\n([^\n])', r'```\n\n\1', content)

        return content.strip()

    def _basic_markdown_format(self, content: str) -> str:
        """Formatage Markdown de base en cas d'erreur"""
        if not content:
            return "## ℹ️ Information\n\nAucune donnée disponible."

        # Détecter le type de contenu pour le bon préfixe
        if "erreur" in content.lower() or "error" in content.lower():
            prefix = "## ❌ Erreur"
        elif "succès" in content.lower() or "success" in content.lower():
            prefix = "## ✅ Succès"
        elif "attention" in content.lower() or "warning" in content.lower():
            prefix = "## ⚠️ Attention"
        else:
            prefix = "## ℹ️ Résultat"

        # Formatage minimal mais propre
        formatted = f"{prefix}\n\n{content}"

        # Échapper les caractères problématiques si nécessaire
        formatted = formatted.replace('`', '`')

        return formatted

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