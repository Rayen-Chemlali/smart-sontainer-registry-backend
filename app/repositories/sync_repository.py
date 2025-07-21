from typing import List
from datetime import datetime
from sqlalchemy.orm import Session
from app.repositories.base_repository import BaseRepository
from app.models.sync_log import SyncLog


class SyncRepository(BaseRepository[SyncLog]):
    def __init__(self, db: Session):
        super().__init__(SyncLog, db)

    def get_recent_logs(self, limit: int = 50) -> List[SyncLog]:
        """Récupère les logs de sync les plus récents"""
        return (self.db.query(SyncLog)
                .order_by(SyncLog.created_at.desc())
                .limit(limit)
                .all())

    def get_by_sync_type(self, sync_type: str) -> List[SyncLog]:
        """Récupère les logs par type de synchronisation"""
        return self.db.query(SyncLog).filter(SyncLog.sync_type == sync_type).all()
