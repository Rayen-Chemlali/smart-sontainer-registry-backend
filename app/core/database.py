# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os
from functools import lru_cache

Base = declarative_base()


class DatabaseManager:
    """Singleton pour la gestion de la base de données"""
    _instance = None
    _engine = None
    _session_factory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._engine is None:
            self._initialize_database()

    def _initialize_database(self):
        """Initialise la connexion à la base de données"""
        database_url = self._get_database_url()

        self._engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False
        )

        self._session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self._engine
        )

    def _get_database_url(self) -> str:
        """Construit l'URL de la base de données"""
        from app.config import settings

        return f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

    def get_session(self) -> Session:
        """Retourne une nouvelle session de base de données"""
        return self._session_factory()

    def create_tables(self):
        """Crée toutes les tables"""
        Base.metadata.create_all(bind=self._engine)

    def drop_tables(self):
        """Supprime toutes les tables"""
        Base.metadata.drop_all(bind=self._engine)


# Instance singleton
db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """Générateur de session pour l'injection de dépendances FastAPI"""
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()


@lru_cache()
def get_database_session() -> Session:
    """Retourne une session de base de données (pour usage direct)"""
    return db_manager.get_session()