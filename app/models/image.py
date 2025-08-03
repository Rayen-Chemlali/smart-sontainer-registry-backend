# app/models/image.py
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float
from datetime import datetime

from app.models import BaseModel


class Image(BaseModel):
    __tablename__ = "images"

    # Informations de base de l'image
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Statut et tracking
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    first_detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Informations détaillées (depuis l'API)
    total_tags = Column(Integer, default=0)
    total_size_bytes = Column(Integer, default=0)
    total_size_mb = Column(Float, default=0.0)

    # Statut de déploiement
    is_deployed = Column(Boolean, default=False, nullable=False, index=True)
    deployed_tags_count = Column(Integer, default=0)

    # Métadonnées supplémentaires
    architecture = Column(String(50), nullable=True)
    os = Column(String(50), nullable=True)

    def __repr__(self):
        return f"<Image(name='{self.name}', active={self.is_active}, deployed={self.is_deployed})>"

    def to_dict(self):
        """Convertit le modèle en dictionnaire"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "first_detected_at": self.first_detected_at.isoformat() if self.first_detected_at else None,
            "total_tags": self.total_tags,
            "total_size_bytes": self.total_size_bytes,
            "total_size_mb": self.total_size_mb,
            "is_deployed": self.is_deployed,
            "deployed_tags_count": self.deployed_tags_count,
            "architecture": self.architecture,
            "os": self.os,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }