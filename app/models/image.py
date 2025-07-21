from sqlalchemy import Column, String, DateTime, Integer, Boolean, BigInteger, Text
from .base import BaseModel


class Image(BaseModel):
    __tablename__ = "images"

    # Identification
    repository = Column(String(255), nullable=False)
    tag = Column(String(255), nullable=False)
    digest = Column(String(255), unique=True, nullable=False)

    # Métadonnées
    size_bytes = Column(BigInteger)
    architecture = Column(String(50))

    # Usage
    last_pulled_at = Column(DateTime)
    pull_count = Column(Integer, default=0)
    is_deployed = Column(Boolean, default=False)

    # Statut
    is_active = Column(Boolean, default=True)
    soft_deleted_at = Column(DateTime)
    backup_location = Column(String(500))