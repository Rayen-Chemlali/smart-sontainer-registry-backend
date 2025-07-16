from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import registry, k8s, overview,chatbot
from app.core.logging import setup_logging

# Configuration du logging
setup_logging()

app = FastAPI(
    title="Smart Registry API",
    description="API pour la gestion intelligente des registries de conteneurs",
    version="1.0.0"
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

if __name__ == "__main__":
    url = "http://localhost:8000/docs"
    print(f"🚀 Smart Registry API démarrée !\nVoici la documentation : {url}")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)