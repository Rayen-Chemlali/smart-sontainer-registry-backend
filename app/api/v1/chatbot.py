from fastapi import APIRouter, Depends, HTTPException
from app.api.schemas.chatbot import ChatRequest, ChatResponse, ChatHealthResponse
from app.services.chatbot_service import ChatbotService
from app.dependencies import get_chatbot_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
        request: ChatRequest,
        chatbot_service: ChatbotService = Depends(get_chatbot_service)
):
    """Endpoint principal pour interagir avec le chatbot"""
    try:
        result = await chatbot_service.process_message(
            request.message,
            request.context
        )
        return result
    except Exception as e:
        logger.error(f"Erreur chat endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement du message: {str(e)}"
        )


@router.get("/health", response_model=ChatHealthResponse)
async def chatbot_health(
        chatbot_service: ChatbotService = Depends(get_chatbot_service)
):
    """Vérifier la santé du chatbot et des services"""
    try:
        services_status = {}

        try:
            overview = chatbot_service.overview_service.get_complete_overview()
            services_status["overview"] = overview.get("kubernetes", {}).get("status") == "connected"
        except:
            services_status["overview"] = False

        try:
            catalog = chatbot_service.registry_service.get_catalog()
            services_status["registry"] = isinstance(catalog, list)
        except:
            services_status["registry"] = False

        try:
            buckets = chatbot_service.s3_client.get_buckets()
            services_status["s3"] = isinstance(buckets, list)
        except:
            services_status["s3"] = False

        groq_available = True
        try:
            test_result = chatbot_service.groq_client.analyze_user_intent("test")
            groq_available = "action" in test_result
        except:
            groq_available = False

        return ChatHealthResponse(
            status="healthy" if groq_available and any(services_status.values()) else "degraded",
            groq_available=groq_available,
            services_available=services_status,
            message="Chatbot opérationnel" if groq_available else "Problème de connexion Groq"
        )

    except Exception as e:
        logger.error(f"Erreur health check: {e}")
        return ChatHealthResponse(
            status="error",
            groq_available=False,
            services_available={},
            message=f"Erreur: {str(e)}"
        )


@router.get("/examples")
async def get_examples():
    """Retourne des exemples d'utilisation du chatbot"""
    return {
        "examples": [
            {
                "category": "Images Registry",
                "commands": [
                    "Liste-moi toutes les images",
                    "Montre-moi les images déployées",
                    "Quelles images ne sont pas déployées?",
                    "Donne-moi les détails de l'image nginx"
                ]
            },
            {
                "category": "Kubernetes",
                "commands": [
                    "Affiche les pods du namespace production",
                    "Liste les deployments",
                    "Montre-moi tous les namespaces",
                    "Quels pods sont en cours d'exécution?"
                ]
            },
            {
                "category": "Vue d'ensemble",
                "commands": [
                    "Donne-moi une vue d'ensemble du système",
                    "Compare le registre et les déploiements",
                    "Quel est le statut général?"
                ]
            },
            {
                "category": "Stockage S3",
                "commands": [
                    "Liste les buckets S3",
                    "Montre-moi le contenu du bucket logs",
                    "Quels sont les buckets disponibles?"
                ]
            }
        ],
        "tips": [
            "Vous pouvez spécifier un namespace: 'pods du namespace production'",
            "Soyez naturel dans vos demandes",
            "Le chatbot comprend le français et l'anglais",
            "Utilisez des termes techniques ou familiers"
        ]
    }