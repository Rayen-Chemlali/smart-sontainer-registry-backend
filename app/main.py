from fastapi import FastAPI
import uvicorn
import asyncio
from contextlib import asynccontextmanager

from app.api.middleware import setup_middlewares
from app.api.router import router
from app.core.logging import setup_logging
from app.dependencies import get_rule_evaluation_worker


setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Démarrage de l'application...")

    worker = None
    worker_task = None

    try:
        worker = get_rule_evaluation_worker()
        worker_task = asyncio.create_task(worker.start())
        worker._task = worker_task
        app.state.worker = worker
        app.state.worker_task = worker_task
        print("✅ Worker des règles démarré en arrière-plan")

    except Exception as e:
        print(f"❌ Erreur au démarrage du worker: {e}")
        app.state.worker = None
        app.state.worker_task = None

    yield

    print("🔄 Arrêt de l'application...")

    if hasattr(app.state, 'worker') and app.state.worker:
        try:
            print("🔄 Arrêt du worker en cours...")
            app.state.worker.stop()

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

setup_middlewares(app)
app.include_router(router)


if __name__ == "__main__":
    url = "http://localhost:8000/docs"
    print(f"🚀 Smart Registry API démarrée !")
    print(f"📚 Documentation : {url}")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)