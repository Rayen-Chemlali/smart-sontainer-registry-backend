from fastapi import FastAPI
import uvicorn
import asyncio
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import registry, k8s, overview, chatbot, rules
from app.core.logging import setup_logging
from app.workers.rule_evaluation_worker import start_rule_worker, get_rule_worker

# Configuration du logging
setup_logging()


# Gestionnaire de contexte pour le cycle de vie de l'application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Démarrage de l'application...")

    # Démarrer le worker en arrière-plan
    worker_task = asyncio.create_task(start_rule_worker())

    # Stocker la tâche pour pouvoir l'arrêter plus tard
    app.state.worker_task = worker_task

    print("✅ Worker des règles démarré en arrière-plan")

    yield

    # Shutdown
    print("🔄 Arrêt de l'application...")

    # Arrêter le worker
    worker = get_rule_worker()
    worker.stop()

    # Annuler la tâche
    if hasattr(app.state, 'worker_task'):
        app.state.worker_task.cancel()
        try:
            await app.state.worker_task
        except asyncio.CancelledError:
            pass

    print("✅ Worker arrêté proprement")


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

# Inclusion des routers
app.include_router(registry.router, prefix="/api/v1")
app.include_router(k8s.router, prefix="/api/v1")
app.include_router(overview.router, prefix="/api/v1")
app.include_router(chatbot.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")  # Nouveau router pour les règles


@app.get("/")
async def root():
    return {
        "message": "Smart Registry API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/worker/status")
async def worker_status():
    """Vérifier le statut du worker"""
    worker = get_rule_worker()
    return {
        "running": worker.running,
        "proposals_count": len(worker.deletion_proposals)
    }






if __name__ == "__main__":
    url = "http://localhost:8000/docs"
    print(f"🚀 Smart Registry API démarrée !\nVoici la documentation : {url}")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)