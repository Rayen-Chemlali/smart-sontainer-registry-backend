from fastapi import FastAPI
import uvicorn
from app.api.v1 import registry, k8s, overview
from app.core.logging import setup_logging

# Configuration du logging
setup_logging()

app = FastAPI(
    title="Smart Registry API",
    description="API pour la gestion intelligente des registries de conteneurs",
    version="1.0.0"
)

# Inclusion des routers
app.include_router(registry.router, prefix="/api/v1")
app.include_router(k8s.router, prefix="/api/v1")
app.include_router(overview.router, prefix="/api/v1")

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

# Lancer automatiquement le serveur si exécuté directement
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
