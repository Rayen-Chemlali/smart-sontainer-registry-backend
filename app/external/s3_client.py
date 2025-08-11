#unused till now
from minio import Minio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class S3Client:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )

    def get_buckets(self) -> List[Dict]:
        """Récupère la liste des buckets"""
        try:
            buckets = self.client.list_buckets()
            return [
                {
                    "name": bucket.name,
                    "creation_date": bucket.creation_date.isoformat() if bucket.creation_date else None
                }
                for bucket in buckets
            ]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des buckets: {e}")
            return []

    def get_objects_in_bucket(self, bucket_name: str) -> List[Dict]:
        """Récupère les objets dans un bucket spécifique"""
        try:
            objects = self.client.list_objects(bucket_name, recursive=True)
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag
                }
                for obj in objects
            ]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des objets du bucket {bucket_name}: {e}")
            return []