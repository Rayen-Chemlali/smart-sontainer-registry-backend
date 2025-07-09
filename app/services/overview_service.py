from typing import Dict
from datetime import datetime
from app.services.registry_service import RegistryService
from app.services.k8s_service import K8sService
from app.external.s3_client import S3Client
import logging

logger = logging.getLogger(__name__)

class OverviewService:
    def __init__(self, s3_client: S3Client, registry_service: RegistryService, k8s_service: K8sService):
        self.s3_client = s3_client
        self.registry_service = registry_service
        self.k8s_service = k8s_service

    def get_complete_overview(self) -> Dict:
        """Vue d'ensemble complète du système"""
        overview = {
            "timestamp": datetime.now().isoformat(),
            "status": {}
        }

        # S3/MinIO
        try:
            buckets = self.s3_client.get_buckets()
            overview["s3"] = {
                "status": "connected",
                "buckets_count": len(buckets),
                "buckets": [b["name"] for b in buckets]
            }
        except Exception as e:
            overview["s3"] = {"status": "error", "error": str(e)}

        # Registry avec statut de déploiement
        try:
            images = self.registry_service.get_images_with_deployment_status()
            deployed_count = len([img for img in images if img["is_deployed"]])

            overview["registry"] = {
                "status": "connected",
                "images_count": len(images),
                "deployed_images_count": deployed_count,
                "deployment_rate": f"{(deployed_count / len(images) * 100):.1f}%" if images else "0%",
                "images": [
                    {
                        "name": img["name"],
                        "tags": len(img["tags"]),
                        "is_deployed": img["is_deployed"]
                    }
                    for img in images
                ]
            }
        except Exception as e:
            overview["registry"] = {"status": "error", "error": str(e)}

        # Kubernetes
        try:
            namespaces = self.k8s_service.get_namespaces()
            pods = self.k8s_service.get_pods("default")
            deployments = self.k8s_service.get_deployments("default")
            deployed_images = self.k8s_service.get_deployed_images()

            overview["kubernetes"] = {
                "status": "connected",
                "namespaces_count": len(namespaces),
                "pods_count": len(pods),
                "deployments_count": len(deployments),
                "running_pods": len([p for p in pods if p["status"] == "Running"]),
                "unique_deployed_images": len(deployed_images)
            }
        except Exception as e:
            overview["kubernetes"] = {"status": "error", "error": str(e)}

        return overview