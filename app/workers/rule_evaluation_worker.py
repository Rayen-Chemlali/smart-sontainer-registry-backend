import asyncio
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.rule_engine import RuleEngine
from app.services.registry_service import RegistryService
from app.core.database import get_db


class RuleEvaluationWorker:
    def __init__(self, registry_service: RegistryService):
        self.registry_service = registry_service
        self.running = False
        self.deletion_proposals = []  # Stockage en mémoire

    def _get_rule_engine(self) -> RuleEngine:
        """Obtient une nouvelle instance du rule engine avec une session DB"""
        # Utilisez votre mécanisme de création de session DB
        db = next(get_db())
        return RuleEngine(db)

    async def start(self):
        """Démarre le worker d'évaluation des règles"""
        self.running = True
        print("🔄 Rule evaluation worker started")

        # Initialiser les règles par défaut au démarrage
        rule_engine = self._get_rule_engine()
        default_rules = rule_engine.initialize_default_rules()
        if default_rules:
            print(f"✅ Initialized {len(default_rules)} default rules")

        while self.running:
            try:
                await self.evaluate_all_images()
                await asyncio.sleep(3600)  # Évaluation toutes les heures
            except Exception as e:
                print(f"❌ Error in rule evaluation: {e}")
                await asyncio.sleep(300)  # Retry après 5 minutes

    def stop(self):
        """Arrête le worker"""
        self.running = False
        print("⏹️ Rule evaluation worker stopped")

    async def evaluate_all_images(self):
        """Évalue toutes les images du registry contre les règles"""
        print("🔍 Starting rule evaluation for all images...")

        rule_engine = self._get_rule_engine()
        active_rules = rule_engine.get_active_rules()

        if not active_rules:
            print("⚠️ No active rules found, skipping evaluation")
            return

        print(f"📋 Found {len(active_rules)} active rules")

        # Utiliser la méthode existante du registry service
        images = self.registry_service.get_filtered_images(
            include_details=True,
            filter_criteria=self.registry_service.ImageFilterCriteria.ALL
        )

        deletion_candidates = []

        for image in images:
            # Traiter chaque tag de l'image
            for detailed_tag in image.get("detailed_tags", []):
                image_data = {
                    "name": f"{image['name']}:{detailed_tag['tag']}",
                    "image_name": image["name"],
                    "tag": detailed_tag["tag"],
                    "tags": [detailed_tag["tag"]],
                    "created_at": detailed_tag.get("created", datetime.utcnow().isoformat()),
                    "size": detailed_tag.get("size", 0),
                    "is_deployed": detailed_tag.get("is_deployed", False),
                    "rank": 0  # Sera calculé si nécessaire pour les règles count_based
                }

                matching_rule_ids = rule_engine.evaluate_image(image_data)

                if matching_rule_ids:
                    # Obtenir les détails des règles correspondantes
                    matching_rules = []
                    for rule_id in matching_rule_ids:
                        rule = rule_engine.get_rule_by_id(rule_id)
                        if rule:
                            matching_rules.append({
                                "id": rule.id,
                                "name": rule.name,
                                "type": rule.rule_type,
                                "description": rule.description
                            })

                    deletion_candidates.append({
                        "image": image_data,
                        "matching_rule_ids": matching_rule_ids,
                        "matching_rules": matching_rules,
                        "evaluation_time": datetime.utcnow().isoformat()
                    })

        if deletion_candidates:
            await self._process_deletion_candidates(deletion_candidates)

        print(f"✅ Rule evaluation completed. Found {len(deletion_candidates)} candidates for deletion")

    async def _process_deletion_candidates(self, candidates: List[Dict[str, Any]]):
        """Traite les candidats à la suppression"""
        print(f"🗑️ Processing {len(candidates)} deletion candidates...")

        for candidate in candidates:
            image_name = candidate["image"]["name"]
            matching_rules = candidate["matching_rules"]
            rule_names = [rule["name"] for rule in matching_rules]

            print(f"📋 Image '{image_name}' matches rules: {rule_names}")

            # Vérifier si l'image est déployée avant de proposer la suppression
            if not candidate["image"]["is_deployed"]:
                await self._create_deletion_proposal(candidate)
            else:
                print(f"⚠️ Image '{image_name}' is deployed, skipping deletion proposal")

    async def _create_deletion_proposal(self, candidate: Dict[str, Any]):
        """Crée une proposition de suppression pour validation admin"""
        rule_descriptions = [
            f"{rule['name']} ({rule['type']})"
            for rule in candidate["matching_rules"]
        ]

        proposal = {
            "id": f"proposal_{int(datetime.utcnow().timestamp() * 1000)}",
            "image_name": candidate["image"]["image_name"],
            "tag": candidate["image"]["tag"],
            "reason": f"Matches rules: {', '.join(rule_descriptions)}",
            "proposed_at": datetime.utcnow().isoformat(),
            "status": "pending_approval",
            "image_data": candidate["image"],
            "matching_rule_ids": candidate["matching_rule_ids"],
            "matching_rules": candidate["matching_rules"]
        }

        # Éviter les doublons
        existing_proposal = next((
            p for p in self.deletion_proposals
            if p["image_name"] == proposal["image_name"]
               and p["tag"] == proposal["tag"]
               and p["status"] == "pending_approval"
        ), None)

        if not existing_proposal:
            self.deletion_proposals.append(proposal)
            print(f"📝 Created deletion proposal for {proposal['image_name']}:{proposal['tag']}")
        else:
            print(f"⚠️ Proposal already exists for {proposal['image_name']}:{proposal['tag']}")

        return proposal

    def get_deletion_proposals(self) -> List[Dict[str, Any]]:
        """Retourne toutes les propositions de suppression"""
        # Nettoyer les anciennes propositions traitées (optionnel)
        # self.deletion_proposals = [
        #     p for p in self.deletion_proposals
        #     if p["status"] == "pending_approval"
        # ]
        return self.deletion_proposals

    def approve_deletion_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Approuve et exécute une proposition de suppression"""
        proposal = next((p for p in self.deletion_proposals if p["id"] == proposal_id), None)

        if not proposal:
            return {"success": False, "message": "Proposition non trouvée"}

        if proposal["status"] != "pending_approval":
            return {"success": False, "message": f"Proposition déjà traitée (status: {proposal['status']})"}

        try:
            # Exécuter la suppression via le registry service
            result = self.registry_service.delete_image_tag(
                proposal["image_name"],
                proposal["tag"]
            )

            if result:
                proposal["status"] = "approved"
                proposal["executed_at"] = datetime.utcnow().isoformat()
                print(f"✅ Approved and deleted {proposal['image_name']}:{proposal['tag']}")
                return {
                    "success": True,
                    "message": f"Suppression de {proposal['image_name']}:{proposal['tag']} exécutée avec succès"
                }
            else:
                proposal["status"] = "failed"
                print(f"❌ Failed to delete {proposal['image_name']}:{proposal['tag']}")
                return {"success": False, "message": "Échec de la suppression dans le registry"}

        except Exception as e:
            proposal["status"] = "failed"
            proposal["error"] = str(e)
            proposal["failed_at"] = datetime.utcnow().isoformat()
            print(f"❌ Error deleting {proposal['image_name']}:{proposal['tag']}: {e}")
            return {"success": False, "message": f"Erreur lors de la suppression: {str(e)}"}

    def reject_deletion_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Rejette une proposition de suppression"""
        proposal = next((p for p in self.deletion_proposals if p["id"] == proposal_id), None)

        if not proposal:
            return {"success": False, "message": "Proposition non trouvée"}

        if proposal["status"] != "pending_approval":
            return {"success": False, "message": f"Proposition déjà traitée (status: {proposal['status']})"}

        proposal["status"] = "rejected"
        proposal["rejected_at"] = datetime.utcnow().isoformat()
        print(f"🚫 Rejected deletion proposal for {proposal['image_name']}:{proposal['tag']}")

        return {
            "success": True,
            "message": f"Proposition de suppression pour {proposal['image_name']}:{proposal['tag']} rejetée"
        }

    def get_proposal_stats(self) -> Dict[str, int]:
        """Retourne des statistiques sur les propositions"""
        stats = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "failed": 0,
            "total": len(self.deletion_proposals)
        }

        for proposal in self.deletion_proposals:
            status = proposal["status"]
            if status == "pending_approval":
                stats["pending"] += 1
            elif status == "approved":
                stats["approved"] += 1
            elif status == "rejected":
                stats["rejected"] += 1
            elif status == "failed":
                stats["failed"] += 1

        return stats


# Variable globale pour le worker (simplification sans DI)
_rule_worker_instance = None


def get_rule_worker():
    """Retourne l'instance du worker (singleton)"""
    global _rule_worker_instance
    if _rule_worker_instance is None:
        from app.external.registry_client import RegistryClient
        from app.external.k8s_client import K8sClient

        # Initialiser les clients (à adapter selon votre configuration)
        registry_client = RegistryClient()
        k8s_client = K8sClient()
        registry_service = RegistryService(registry_client, k8s_client)

        _rule_worker_instance = RuleEvaluationWorker(registry_service)

    return _rule_worker_instance


async def start_rule_worker():
    """Démarre le worker de règles"""
    worker = get_rule_worker()
    await worker.start()