from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.base_repository import BaseRepository
from app.models.image import Image


class ImageRepository(BaseRepository[Image]):
    def __init__(self, db: Session):
        super().__init__(Image, db)

    def get_by_name_and_tag(self, name: str, tag: str) -> Optional[Image]:
        """Récupère une image par nom et tag"""
        return self.db.query(Image).filter(
            Image.name == name,
            Image.tag == tag
        ).first()

    def get_by_registry_url(self, registry_url: str) -> List[Image]:
        """Récupère toutes les images d'un registry"""
        return self.db.query(Image).filter(Image.registry_url == registry_url).all()