# app/repositories/image_repository.py
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from datetime import datetime, timedelta
from app.repositories.base_repository import BaseRepository
from app.models.image import Image
import logging

logger = logging.getLogger(__name__)


class ImageRepository(BaseRepository[Image]):
    """Repository spécialisé pour la gestion des images"""

    def __init__(self, db: Session):
        super().__init__(Image, db)

    def get_by_name(self, name: str) -> Optional[Image]:
        """Récupère une image par son nom"""
        try:
            return self.db.query(self.model).filter(self.model.name == name).first()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'image {name}: {e}")
            self.db.rollback()
            return None

    def get_active_images(self, skip: int = 0, limit: int = 100) -> List[Image]:
        """Récupère toutes les images actives"""
        try:
            return (self.db.query(self.model)
                    .filter(self.model.is_active == True)
                    .order_by(desc(self.model.last_seen_at))
                    .offset(skip)
                    .limit(limit)
                    .all())
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images actives: {e}")
            self.db.rollback()
            return []

    def get_inactive_images(self, skip: int = 0, limit: int = 100) -> List[Image]:
        """Récupère toutes les images inactives"""
        try:
            return (self.db.query(self.model)
                    .filter(self.model.is_active == False)
                    .order_by(desc(self.model.last_seen_at))
                    .offset(skip)
                    .limit(limit)
                    .all())
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images inactives: {e}")
            self.db.rollback()
            return []

    def get_deployed_images(self, skip: int = 0, limit: int = 100) -> List[Image]:
        """Récupère toutes les images déployées"""
        try:
            return (self.db.query(self.model)
                    .filter(self.model.is_deployed == True)
                    .order_by(desc(self.model.last_seen_at))
                    .offset(skip)
                    .limit(limit)
                    .all())
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images déployées: {e}")
            self.db.rollback()
            return []

    def get_images_not_seen_since(self, days: int) -> List[Image]:
        """Récupère les images non vues depuis X jours"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            return (self.db.query(self.model)
                    .filter(self.model.last_seen_at < cutoff_date)
                    .order_by(asc(self.model.last_seen_at))
                    .all())
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images anciennes: {e}")
            self.db.rollback()
            return []

    def create_or_update_image(self, image_data: Dict[str, Any]) -> Image:
        """Crée une nouvelle image ou met à jour une existante"""
        try:
            image_name = image_data.get("name")
            if not image_name:
                raise ValueError("Le nom de l'image est requis")

            # Chercher l'image existante
            existing_image = self.get_by_name(image_name)

            if existing_image:
                # Mise à jour de l'image existante
                existing_image.last_seen_at = datetime.utcnow()
                existing_image.is_active = True

                # Mettre à jour les autres champs depuis les données API
                existing_image.total_tags = image_data.get("tag_count", existing_image.total_tags)
                existing_image.total_size_bytes = image_data.get("total_size", existing_image.total_size_bytes)
                existing_image.total_size_mb = image_data.get("total_size_mb", existing_image.total_size_mb)
                existing_image.is_deployed = image_data.get("is_deployed", existing_image.is_deployed)
                existing_image.deployed_tags_count = image_data.get("deployed_tags_count",
                                                                    existing_image.deployed_tags_count)

                # Mise à jour optionnelle de la description si fournie
                if image_data.get("description"):
                    existing_image.description = image_data.get("description")

                # Extraire l'architecture et l'OS depuis detailed_tags si disponible
                detailed_tags = image_data.get("detailed_tags", [])
                if detailed_tags:
                    first_tag = detailed_tags[0]
                    existing_image.architecture = first_tag.get("architecture", existing_image.architecture)
                    existing_image.os = first_tag.get("os", existing_image.os)

                self.db.commit()
                self.db.refresh(existing_image)
                logger.info(f"Image mise à jour: {image_name}")
                return existing_image

            else:
                # Création d'une nouvelle image
                now = datetime.utcnow()

                # Extraire l'architecture et l'OS depuis detailed_tags si disponible
                architecture = None
                os_type = None
                detailed_tags = image_data.get("detailed_tags", [])
                if detailed_tags:
                    first_tag = detailed_tags[0]
                    architecture = first_tag.get("architecture")
                    os_type = first_tag.get("os")

                new_image = Image(
                    name=image_name,
                    description=image_data.get("description"),
                    is_active=True,
                    last_seen_at=now,
                    first_detected_at=now,  # Première détection
                    total_tags=image_data.get("tag_count", 0),
                    total_size_bytes=image_data.get("total_size", 0),
                    total_size_mb=image_data.get("total_size_mb", 0.0),
                    is_deployed=image_data.get("is_deployed", False),
                    deployed_tags_count=image_data.get("deployed_tags_count", 0),
                    architecture=architecture,
                    os=os_type
                )

                self.db.add(new_image)
                self.db.commit()
                self.db.refresh(new_image)
                logger.info(f"Nouvelle image créée: {image_name}")
                return new_image

        except Exception as e:
            logger.error(f"Erreur lors de la création/mise à jour de l'image {image_data.get('name', 'Unknown')}: {e}")
            self.db.rollback()
            raise e

    def mark_images_as_inactive(self, active_image_names: List[str]) -> int:
        """Marque toutes les images non présentes dans la liste comme inactives"""
        try:
            # Récupérer toutes les images actuellement actives
            current_active_images = self.get_active_images(limit=1000)  # Limite élevée pour récupérer toutes

            inactive_count = 0
            for image in current_active_images:
                if image.name not in active_image_names:
                    image.is_active = False
                    inactive_count += 1
                    logger.info(f"Image marquée comme inactive: {image.name}")

            if inactive_count > 0:
                self.db.commit()
                logger.info(f"{inactive_count} images marquées comme inactives")

            return inactive_count

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du statut des images: {e}")
            self.db.rollback()
            return 0

    def bulk_sync_images(self, registry_images: List[Dict[str, Any]]) -> Dict[str, int]:
        """Synchronise en masse les images depuis le registry"""
        try:
            stats = {
                "created": 0,
                "updated": 0,
                "marked_inactive": 0,
                "errors": 0
            }

            active_image_names = []

            # Traiter chaque image du registry
            for image_data in registry_images:
                try:
                    image = self.create_or_update_image(image_data)
                    active_image_names.append(image.name)

                    if image.created_at == image.updated_at:
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1

                except Exception as e:
                    logger.error(f"Erreur lors du traitement de l'image {image_data.get('name', 'Unknown')}: {e}")
                    stats["errors"] += 1

            # Marquer les images absentes comme inactives
            stats["marked_inactive"] = self.mark_images_as_inactive(active_image_names)

            logger.info(f"Synchronisation terminée: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation en masse: {e}")
            self.db.rollback()
            return {"created": 0, "updated": 0, "marked_inactive": 0, "errors": 1}

    def get_statistics(self) -> Dict[str, Any]:
        """Récupère des statistiques sur les images"""
        try:
            total_images = self.count()
            active_count = self.db.query(self.model).filter(self.model.is_active == True).count()
            inactive_count = self.db.query(self.model).filter(self.model.is_active == False).count()
            deployed_count = self.db.query(self.model).filter(self.model.is_deployed == True).count()

            # Images récemment vues (dernières 24h)
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_count = self.db.query(self.model).filter(self.model.last_seen_at >= recent_cutoff).count()

            # Images anciennes (pas vues depuis 30 jours)
            old_cutoff = datetime.utcnow() - timedelta(days=30)
            old_count = self.db.query(self.model).filter(self.model.last_seen_at < old_cutoff).count()

            return {
                "total_images": total_images,
                "active_images": active_count,
                "inactive_images": inactive_count,
                "deployed_images": deployed_count,
                "recent_images": recent_count,
                "old_images": old_count,
                "activity_rate": f"{(active_count / total_images * 100):.1f}%" if total_images > 0 else "0%",
                "deployment_rate": f"{(deployed_count / total_images * 100):.1f}%" if total_images > 0 else "0%"
            }

        except Exception as e:
            logger.error(f"Erreur lors du calcul des statistiques: {e}")
            return {
                "total_images": 0,
                "active_images": 0,
                "inactive_images": 0,
                "deployed_images": 0,
                "recent_images": 0,
                "old_images": 0,
                "activity_rate": "0%",
                "deployment_rate": "0%"
            }

    def delete_inactive_images(self, older_than_days: int = 90) -> Dict[str, Any]:
        """Supprime les images inactives plus anciennes que X jours"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

            # Récupérer les images à supprimer
            images_to_delete = (self.db.query(self.model)
                                .filter(self.model.is_active == False)
                                .filter(self.model.last_seen_at < cutoff_date)
                                .all())

            deleted_names = [img.name for img in images_to_delete]
            deleted_count = len(images_to_delete)

            # Supprimer les images
            for image in images_to_delete:
                self.db.delete(image)

            self.db.commit()

            logger.info(f"{deleted_count} images inactives supprimées de la base de données")

            return {
                "success": True,
                "deleted_count": deleted_count,
                "deleted_images": deleted_names,
                "cutoff_date": cutoff_date.isoformat()
            }

        except Exception as e:
            logger.error(f"Erreur lors de la suppression des images inactives: {e}")
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
                "deleted_count": 0
            }