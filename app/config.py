from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
from pathlib import Path

root_dir = Path(__file__).parent.parent
env_path = root_dir / ".env"
load_dotenv(env_path)

class Settings(BaseSettings):
    # MinIO/S3
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool

    # Registry
    REGISTRY_URL: str

    # Groq
    GROQ_API_KEY: str

    # PostgreSQL Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str

    # Application
    APP_NAME: str
    DEBUG: bool

    # Security (JWT)
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 600

    # Database URL
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = "ignore"
        case_sensitive = True

try:
    print("🔧 Creating Settings instance...")
    settings = Settings()
    print("✅ Settings created successfully!")
    print(f"✅ MINIO_ENDPOINT: {settings.MINIO_ENDPOINT}")
    print(f"✅ POSTGRES_USER: {settings.POSTGRES_USER}")
    print(f"✅ APP_NAME: {settings.APP_NAME}")
except Exception as e:
    print(f"❌ Settings creation failed: {e}")
    print(f"❌ Available environment variables:")
    for key, value in os.environ.items():
        if any(prefix in key for prefix in ['MINIO', 'POSTGRES', 'GROQ', 'REGISTRY', 'APP', 'DEBUG']):
            print(f"   {key}: {'*' * min(8, len(value)) if 'KEY' in key or 'PASSWORD' in key else value}")
    raise