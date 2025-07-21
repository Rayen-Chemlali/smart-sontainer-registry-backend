from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.base_repository import BaseRepository
from app.models.deployment import Deployment


class DeploymentRepository(BaseRepository[Deployment]):
    def __init__(self, db: Session):
        super().__init__(Deployment, db)

    def get_by_namespace(self, namespace: str) -> List[Deployment]:
        """Récupère tous les déploiements d'un namespace"""
        return self.db.query(Deployment).filter(Deployment.namespace == namespace).all()

    def get_by_image_id(self, image_id: int) -> List[Deployment]:
        """Récupère tous les déploiements utilisant une image"""
        return self.db.query(Deployment).filter(Deployment.image_id == image_id).all()