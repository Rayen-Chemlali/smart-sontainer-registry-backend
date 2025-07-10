from setuptools import setup, find_packages

setup(
    name="smart-registry-backend",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi==0.104.1",
        "uvicorn==0.24.0",
        "sqlalchemy==2.0.23",
        "alembic==1.13.1",
        "pydantic==2.5.0",
        "redis==5.0.1",
        "boto3==1.34.0",
        "kubernetes==28.1.0",
        "python-multipart==0.0.6",
        "python-jose[cryptography]==3.3.0",
        "pytest==7.4.3",
        "pytest-asyncio==0.21.1",
        "httpx==0.25.2",
    ],
    python_requires=">=3.11",
) 