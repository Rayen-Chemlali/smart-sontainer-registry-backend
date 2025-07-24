from fastapi import FastAPI
import uvicorn
import asyncio
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import registry, k8s, overview, chatbot, rules, auth
from app.core.logging import setup_logging
from app.dependencies import get_rule_evaluation_worker

# Configuration du logging
setup_logging()


# Gestionnaire de contexte pour le cycle de vie de l'application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Démarrage de l'application...")

    worker = None
    worker_task = None

    try:
        # Obtenir le worker via le système de dépendances
        worker = get_rule_evaluation_worker()

        # Démarrer le worker en arrière-plan avec gestion d'erreur
        worker_task = asyncio.create_task(worker.start())
        worker._task = worker_task  # Tracker la tâche pour le health check

        # Stocker pour pouvoir l'arrêter plus tard
        app.state.worker = worker
        app.state.worker_task = worker_task

        print("✅ Worker des règles démarré en arrière-plan")

    except Exception as e:
        print(f"❌ Erreur au démarrage du worker: {e}")
        # L'application peut continuer sans le worker
        app.state.worker = None
        app.state.worker_task = None

    yield

    # Shutdown
    print("🔄 Arrêt de l'application...")

    # Arrêter le worker proprement
    if hasattr(app.state, 'worker') and app.state.worker:
        try:
            print("🔄 Arrêt du worker en cours...")
            app.state.worker.stop()

            # Attendre l'arrêt avec timeout
            if hasattr(app.state, 'worker_task') and app.state.worker_task:
                app.state.worker_task.cancel()
                try:
                    await asyncio.wait_for(app.state.worker_task, timeout=10.0)
                    print("✅ Worker arrêté proprement")
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    print("⚠️ Worker forcé à s'arrêter (timeout ou annulation)")

        except Exception as e:
            print(f"❌ Erreur lors de l'arrêt du worker: {e}")

    print("✅ Application arrêtée proprement")


app = FastAPI(
    title="Smart Registry API",
    description="API pour la gestion intelligente des registries de conteneurs",
    version="1.0.0",
    lifespan=lifespan
)

# Ajout du middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routers - Auth en premier pour l'ordre logique
app.include_router(auth.router, prefix="/api/v1")  # 🔐 Authentification
app.include_router(registry.router, prefix="/api/v1")
app.include_router(k8s.router, prefix="/api/v1")
app.include_router(overview.router, prefix="/api/v1")
app.include_router(chatbot.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Endpoint public - pas d'authentification requise"""
    return {
        "message": "Smart Registry API",
        "version": "1.0.0",
        "docs": "/docs",
        "auth": {
            "login": "/api/v1/auth/login",
            "register": "/api/v1/auth/register"
        }
    }


@app.get("/health")
async def health():
    """Health check - endpoint public"""
    return {"status": "healthy"}


@app.get("/worker/status")
async def worker_status():
    """Vérifier le statut du worker - endpoint public pour monitoring"""
    try:
        worker = get_rule_evaluation_worker()

        # Vérifications de santé détaillées
        is_running = worker.running
        has_task = hasattr(worker, '_task') and worker._task is not None
        task_done = worker._task.done() if has_task else True
        is_healthy = is_running and has_task and not task_done

        return {
            "running": is_running,
            "healthy": is_healthy,
            "proposals_count": len(worker.deletion_proposals),
            "task_exists": has_task,
            "task_done": task_done,
            "status": "healthy" if is_healthy else "unhealthy"
        }

    except Exception as e:
        return {
            "running": False,
            "healthy": False,
            "error": str(e),
            "status": "error"
        }


@app.get("/worker/proposals")
async def worker_proposals():
    """Obtenir les propositions de suppression - endpoint public pour monitoring"""
    try:
        worker = get_rule_evaluation_worker()
        proposals = worker.get_deletion_proposals()
        stats = worker.get_proposal_stats()

        return {
            "proposals": proposals,
            "statistics": stats,
            "total_proposals": len(proposals)
        }

    except Exception as e:
        return {
            "error": str(e),
            "proposals": [],
            "statistics": {},
            "total_proposals": 0
        }


@app.post("/worker/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    """Approuver une proposition de suppression - endpoint public pour demo"""
    try:
        worker = get_rule_evaluation_worker()
        result = worker.approve_deletion_proposal(proposal_id)
        return result

    except Exception as e:
        return {
            "success": False,
            "message": f"Erreur lors de l'approbation: {str(e)}"
        }


@app.post("/worker/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    """Rejeter une proposition de suppression - endpoint public pour demo"""
    try:
        worker = get_rule_evaluation_worker()
        result = worker.reject_deletion_proposal(proposal_id)
        return result

    except Exception as e:
        return {
            "success": False,
            "message": f"Erreur lors du rejet: {str(e)}"
        }


@app.post("/worker/evaluate")
async def trigger_evaluation():
    """Déclencher manuellement une évaluation - endpoint pour tests"""
    try:
        worker = get_rule_evaluation_worker()

        if not worker.running:
            return {
                "success": False,
                "message": "Worker n'est pas en cours d'exécution"
            }

        # Lancer l'évaluation en arrière-plan
        asyncio.create_task(worker.evaluate_all_images())

        return {
            "success": True,
            "message": "Évaluation déclenchée manuellement"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Erreur lors du déclenchement: {str(e)}"
        }


if __name__ == "__main__":
    url = "http://localhost:8000/docs"
    print(f"🚀 Smart Registry API démarrée !")
    print(f"📚 Documentation : {url}")
    print(f"🔍 Worker Status : http://localhost:8000/worker/status")
    print(f"📋 Worker Proposals : http://localhost:8000/worker/proposals")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)