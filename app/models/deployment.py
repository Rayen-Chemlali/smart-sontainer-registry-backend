from sqlalchemy import Column, String, DateTime, Integer, Boolean
from .base import BaseModel


class Deployment(BaseModel):
    __tablename__ = "deployments"

    # Kubernetes info
    name = Column(String(255), nullable=False)
    namespace = Column(String(255), nullable=False)
    cluster = Column(String(255), nullable=False)

    # Image utilisée
    image_digest = Column(String(255), nullable=False)

    # Statut
    is_active = Column(Boolean, default=True)
    replicas = Column(Integer)
    last_seen_at = Column(DateTime)
