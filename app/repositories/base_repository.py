# app/repositories/base_repository.py
from typing import TypeVar, Generic, List, Optional, Type, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import Base

# Type générique pour les modèles
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Repository générique pour les opérations CRUD de base"""

    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get_by_id(self, id: int) -> Optional[ModelType]:
        """Récupère un enregistrement par son ID"""
        try:
            return self.db.query(self.model).filter(self.model.id == id).first()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Récupère tous les enregistrements avec pagination"""
        try:
            return self.db.query(self.model).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def get_by_field(self, field: str, value: Any) -> Optional[ModelType]:
        """Récupère un enregistrement par un champ spécifique"""
        try:
            return self.db.query(self.model).filter(getattr(self.model, field) == value).first()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def get_many_by_field(self, field: str, value: Any, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Récupère plusieurs enregistrements par un champ spécifique"""
        try:
            return (self.db.query(self.model)
                    .filter(getattr(self.model, field) == value)
                    .offset(skip)
                    .limit(limit)
                    .all())
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def create(self, obj_data: Dict[str, Any]) -> ModelType:
        """Crée un nouvel enregistrement"""
        try:
            db_obj = self.model(**obj_data)
            self.db.add(db_obj)
            self.db.commit()
            self.db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def update(self, id: int, obj_data: Dict[str, Any]) -> Optional[ModelType]:
        """Met à jour un enregistrement existant"""
        try:
            db_obj = self.get_by_id(id)
            if db_obj:
                for field, value in obj_data.items():
                    if hasattr(db_obj, field):
                        setattr(db_obj, field, value)
                self.db.commit()
                self.db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def delete(self, id: int) -> bool:
        """Supprime un enregistrement"""
        try:
            db_obj = self.get_by_id(id)
            if db_obj:
                self.db.delete(db_obj)
                self.db.commit()
                return True
            return False
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def count(self) -> int:
        """Compte le nombre total d'enregistrements"""
        try:
            return self.db.query(self.model).count()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def exists(self, id: int) -> bool:
        """Vérifie si un enregistrement existe"""
        try:
            return self.db.query(self.model).filter(self.model.id == id).first() is not None
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def bulk_create(self, objects_data: List[Dict[str, Any]]) -> List[ModelType]:
        """Crée plusieurs enregistrements en une fois"""
        try:
            db_objects = [self.model(**obj_data) for obj_data in objects_data]
            self.db.add_all(db_objects)
            self.db.commit()
            for obj in db_objects:
                self.db.refresh(obj)
            return db_objects
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e