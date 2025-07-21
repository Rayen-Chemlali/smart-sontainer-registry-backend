from sqlalchemy import Column, String, DateTime, Integer, Text
from .base import BaseModel


class SyncLog(BaseModel):
    __tablename__ = "sync_logs"

    operation = Column(String(100), nullable=False)  # sync_s3, sync_k8s
    status = Column(String(50), nullable=False)  # success, failed, running

    # Résultats
    items_processed = Column(Integer, default=0)
    items_created = Column(Integer, default=0)
    items_updated = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Erreurs
    error_message = Column(Text)