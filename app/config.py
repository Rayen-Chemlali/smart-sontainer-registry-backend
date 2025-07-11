from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MinIO/S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_SECURE: bool = False

    # Registry
    REGISTRY_URL: str = "http://localhost:5000"

    # Groq
    GROQ_API_KEY: str = "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"

    class Config:
        env_file = ".env"


settings = Settings()