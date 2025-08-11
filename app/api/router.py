from fastapi import APIRouter
import asyncio
from app.api.v1 import registry, k8s, overview, chatbot, rules, auth
from app.dependencies import get_rule_evaluation_worker

router = APIRouter()

router.include_router(auth.router, prefix="/api/v1")
router.include_router(registry.router, prefix="/api/v1")
router.include_router(k8s.router, prefix="/api/v1")
router.include_router(overview.router, prefix="/api/v1")
router.include_router(chatbot.router, prefix="/api/v1")
router.include_router(rules.router, prefix="/api/v1")

@router.get("/")
async def root():
    return {
        "message": "Smart Registry API",
        "version": "1.0.0",
        "docs": "/docs",
        "auth": {
            "login": "/api/v1/auth/login",
            "register": "/api/v1/auth/register"
        }
    }

@router.get("/health")
async def health():
    return {"status": "healthy"}

@router.get("/worker/status")
async def worker_status():
    try:
        worker = get_rule_evaluation_worker()
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

@router.get("/worker/proposals")
async def worker_proposals():
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

@router.post("/worker/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    try:
        worker = get_rule_evaluation_worker()
        result = worker.approve_deletion_proposal(proposal_id)
        return result

    except Exception as e:
        return {
            "success": False,
            "message": f"Erreur lors de l'approbation: {str(e)}"
        }

@router.post("/worker/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    try:
        worker = get_rule_evaluation_worker()
        result = worker.reject_deletion_proposal(proposal_id)
        return result

    except Exception as e:
        return {
            "success": False,
            "message": f"Erreur lors du rejet: {str(e)}"
        }

@router.post("/worker/evaluate")
async def trigger_evaluation():
    try:
        worker = get_rule_evaluation_worker()

        if not worker.running:
            return {
                "success": False,
                "message": "Worker n'est pas en cours d'exécution"
            }

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