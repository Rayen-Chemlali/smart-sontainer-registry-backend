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
        self.deletion_proposals = []
        self._task = None  # Ajouter pour tracker la tâche
        # NOUVEAU: Stocker les derniers résultats d'évaluation
        self.last_evaluation_results = {
            "timestamp": None,
            "summary": {},
            "matching_images": [],
            "non_matching_images": [],
            "evaluation_stats": {},
            "errors": []
        }
    def _get_rule_engine(self) -> RuleEngine:
        """Obtient une nouvelle instance du rule engine avec une session DB"""
        from app.dependencies import get_rule_engine, get_db
        db = next(get_db())
        try:
            return RuleEngine(db)
        finally:
            db.close()  # CORRECTION : Fermer la session

    async def start(self):
        """Démarre le worker d'évaluation des règles"""
        if self.running:
            return

        self.running = True
        print("🔄 Rule evaluation worker started")

        # Initialiser les règles par défaut au démarrage
        try:
            rule_engine = self._get_rule_engine()
            default_rules = rule_engine.initialize_default_rules()
            if default_rules:
                print(f"✅ Initialized {len(default_rules)} default rules")
        except Exception as e:
            print(f"❌ Error initializing rules: {e}")

        # Boucle principale
        while self.running:
            try:
                await self.evaluate_all_images()
                await asyncio.sleep(3600)  # Évaluation toutes les heures
            except asyncio.CancelledError:
                print("🔄 Worker cancelled")
                break
            except Exception as e:
                print(f"❌ Error in rule evaluation: {e}")
                if self.running:  # Ne retry que si pas en cours d'arrêt
                    await asyncio.sleep(300)  # Retry après 5 minutes

        print("⏹️ Rule evaluation worker stopped")

    def stop(self):
        """Arrête le worker"""
        self.running = False

    def is_healthy(self) -> bool:
        """Vérifier si le worker est en bonne santé"""
        return self.running and self._task is not None and not self._task.done()

    async def evaluate_all_images(self) -> Dict[str, Any]:
        """Évalue toutes les images et RETOURNE les résultats détaillés"""
        print("🔍 Starting rule evaluation for all images...")

        evaluation_start = datetime.utcnow()

        # Initialiser les résultats
        results = {
            "timestamp": evaluation_start.isoformat(),
            "summary": {
                "total_images_scanned": 0,
                "matching_images_count": 0,
                "non_matching_images_count": 0,
                "deployed_images_skipped": 0,
                "errors_count": 0
            },
            "matching_images": [],
            "non_matching_images": [],
            "evaluation_stats": {
                "rules_applied": 0,
                "evaluation_duration_seconds": 0,
                "images_per_second": 0
            },
            "active_rules": [],
            "errors": []
        }

        try:
            # 1️⃣ Récupérer le moteur de règles et les règles actives
            rule_engine = self._get_rule_engine()
            active_rules = rule_engine.get_active_rules()

            if not active_rules:
                results["errors"].append("No active rules found")
                print("⚠️ No active rules found, skipping evaluation")
                self.last_evaluation_results = results
                return results

            # Stocker les règles actives dans les résultats
            results["active_rules"] = [
                {
                    "id": rule.id,
                    "name": rule.name,
                    "type": rule.rule_type,
                    "description": rule.description,
                    "conditions": rule.conditions,
                    "is_active": rule.is_active
                }
                for rule in active_rules
            ]
            results["evaluation_stats"]["rules_applied"] = len(active_rules)

            print(f"📋 Found {len(active_rules)} active rules")

            # 2️⃣ Récupérer toutes les images
            images = self.registry_service.get_filtered_images(
                include_details=True,
                filter_criteria=self.registry_service.ImageFilterCriteria.ALL.value
            )

            results["summary"]["total_images_scanned"] = sum(
                len(image.get("detailed_tags", [])) for image in images
            )

            # 3️⃣ Évaluer chaque image/tag
            for image in images:
                for detailed_tag in image.get("detailed_tags", []):
                    try:
                        # Préparer les données d'image
                        image_data = {
                            "name": f"{image['name']}:{detailed_tag['tag']}",
                            "image_name": image["name"],
                            "tag": detailed_tag["tag"],
                            "tags": [detailed_tag["tag"]],
                            "created_at": detailed_tag.get("created", datetime.utcnow().isoformat()),
                            "size": detailed_tag.get("size", 0),
                            "is_deployed": detailed_tag.get("is_deployed", False),
                            "rank": 0,
                            "digest": detailed_tag.get("digest"),
                            "architecture": detailed_tag.get("architecture"),
                            "os": detailed_tag.get("os")
                        }

                        # Skip les images déployées mais les compter
                        if image_data["is_deployed"]:
                            results["summary"]["deployed_images_skipped"] += 1
                            results["non_matching_images"].append({
                                "image": image_data,
                                "matching_rules": [],
                                "reason": "Image is deployed - skipped for safety",
                                "evaluation_time": datetime.utcnow().isoformat()
                            })
                            continue

                        # 4️⃣ ÉVALUATION CONTRE LES RÈGLES
                        matching_rule_details = rule_engine.evaluate_image(image_data)

                        # 5️⃣ Organiser les résultats
                        evaluation_result = {
                            "image": image_data,
                            "matching_rules": matching_rule_details,
                            "evaluation_time": datetime.utcnow().isoformat()
                        }

                        if matching_rule_details:
                            # IMAGE MATCHE des règles
                            results["matching_images"].append(evaluation_result)
                            results["summary"]["matching_images_count"] += 1

                            # Créer proposition de suppression si pas déjà fait
                            await self._create_deletion_proposal({
                                "image": image_data,
                                "matching_rule_ids": [rule["rule_id"] for rule in matching_rule_details],
                                "matching_rules": matching_rule_details,
                                "evaluation_time": evaluation_result["evaluation_time"]
                            })
                        else:
                            # IMAGE NE MATCHE PAS
                            evaluation_result["reason"] = "No rules matched"
                            results["non_matching_images"].append(evaluation_result)
                            results["summary"]["non_matching_images_count"] += 1

                    except Exception as e:
                        error_msg = f"Error evaluating {image.get('name', 'unknown')}:{detailed_tag.get('tag', 'unknown')}: {str(e)}"
                        results["errors"].append(error_msg)
                        results["summary"]["errors_count"] += 1
                        print(f"❌ {error_msg}")

            # 6️⃣ Calculer les statistiques finales
            evaluation_end = datetime.utcnow()
            duration = (evaluation_end - evaluation_start).total_seconds()
            results["evaluation_stats"]["evaluation_duration_seconds"] = round(duration, 2)

            if duration > 0:
                results["evaluation_stats"]["images_per_second"] = round(
                    results["summary"]["total_images_scanned"] / duration, 2
                )

            # 7️⃣ Stocker les résultats pour consultation ultérieure
            self.last_evaluation_results = results

            print(f"✅ Rule evaluation completed:")
            print(f"   📊 Total images scanned: {results['summary']['total_images_scanned']}")
            print(f"   ✅ Matching images: {results['summary']['matching_images_count']}")
            print(f"   ❌ Non-matching images: {results['summary']['non_matching_images_count']}")
            print(f"   🛡️ Deployed images skipped: {results['summary']['deployed_images_skipped']}")
            print(f"   ⚠️ Errors: {results['summary']['errors_count']}")
            print(f"   ⏱️ Duration: {results['evaluation_stats']['evaluation_duration_seconds']}s")

            return results

        except Exception as e:
            error_msg = f"Critical error in rule evaluation: {str(e)}"
            results["errors"].append(error_msg)
            results["summary"]["errors_count"] += 1
            self.last_evaluation_results = results
            print(f"💥 {error_msg}")
            return results

    def get_last_evaluation_results(self) -> Dict[str, Any]:
        """Retourne les derniers résultats d'évaluation"""
        return self.last_evaluation_results

    def get_evaluation_summary(self) -> Dict[str, Any]:
        """Retourne un résumé des derniers résultats"""
        if not self.last_evaluation_results.get("timestamp"):
            return {"error": "No evaluation results available"}

        return {
            "last_evaluation": self.last_evaluation_results["timestamp"],
            "summary": self.last_evaluation_results["summary"],
            "stats": self.last_evaluation_results["evaluation_stats"],
            "active_rules_count": len(self.last_evaluation_results.get("active_rules", [])),
            "has_errors": len(self.last_evaluation_results.get("errors", [])) > 0
        }

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


