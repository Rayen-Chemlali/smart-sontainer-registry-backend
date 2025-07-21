#!/usr/bin/env python3
"""
Debug script to troubleshoot .env loading issues
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

print("=== ENVIRONMENT DEBUGGING ===\n")
print(f"Python executable: {sys.executable}")
print(f"Current working directory: {Path.cwd()}")
print(f"Script location: {Path(__file__).parent}")
print(f"Python path: {sys.path[:3]}...")

# Check different .env locations
env_locations = [
    Path.cwd() / ".env",
    Path(__file__).parent / ".env",
    Path(__file__).parent.parent / ".env",
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]

print("\n=== CHECKING .ENV FILE LOCATIONS ===")
env_found = None
for i, env_path in enumerate(env_locations):
    exists = env_path.exists()
    print(f"{i + 1}. {env_path}")
    print(f"   Exists: {exists}")
    if exists:
        print(f"   Size: {env_path.stat().st_size} bytes")
        if env_found is None:
            env_found = env_path

print(f"\n=== LOADING .ENV FILE ===")
if env_found:
    print(f"Using: {env_found}")
    load_dotenv(env_found, verbose=True)

    # Read file content
    with open(env_found, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"\n.env file content preview (first 500 chars):")
    print("-" * 50)
    print(content[:500])
    print("-" * 50)

    # Check for BOM or encoding issues
    with open(env_found, 'rb') as f:
        raw_content = f.read()[:50]
    print(f"\nRaw bytes (first 50): {raw_content}")

else:
    print("❌ No .env file found in any expected location!")

print(f"\n=== ENVIRONMENT VARIABLES CHECK ===")
required_vars = [
    "MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_SECURE",
    "REGISTRY_URL", "GROQ_API_KEY", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "APP_NAME", "DEBUG"
]

for var in required_vars:
    value = os.getenv(var)
    if value:
        display_value = f"[{len(value)} chars]" if "KEY" in var or "PASSWORD" in var else value
        print(f"✓ {var} = {display_value}")
    else:
        print(f"✗ {var} = None")

print(f"\n=== ALL ENVIRONMENT VARIABLES ===")
env_vars = {k: v for k, v in os.environ.items() if
            any(req in k for req in ['MINIO', 'POSTGRES', 'GROQ', 'REGISTRY', 'APP', 'DEBUG'])}
for k, v in env_vars.items():
    display_value = f"[{len(v)} chars]" if "KEY" in k or "PASSWORD" in k else v
    print(f"{k} = {display_value}")

print(f"\n=== PYDANTIC SETTINGS TEST ===")
try:
    from pydantic_settings import BaseSettings


    class TestSettings(BaseSettings):
        MINIO_ENDPOINT: str = "default_value"

        class Config:
            env_file = env_found if env_found else ".env"
            env_file_encoding = 'utf-8'


    test_settings = TestSettings()
    print(f"✓ Pydantic can load: MINIO_ENDPOINT = {test_settings.MINIO_ENDPOINT}")

except Exception as e:
    print(f"✗ Pydantic settings error: {e}")

print("\n=== RECOMMENDATIONS ===")
if not env_found:
    print("1. Create a .env file in your project root")
elif not any(os.getenv(var) for var in required_vars):
    print("1. .env file exists but variables aren't loaded")
    print("2. Check for encoding issues (BOM, special characters)")
    print("3. Try recreating the .env file")
else:
    print("Environment seems to be loaded correctly!")