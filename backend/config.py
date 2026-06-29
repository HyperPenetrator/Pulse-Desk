import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///healthify.db"
    USE_MOCK_AUTH: bool = True
    JWT_SECRET_KEY: str = "supersecretkeyforlocaldevelopment"
    JWT_ALGORITHM: str = "HS256"
    FIREBASE_PROJECT_ID: str = ""
    REFERENCE_DATA_SOURCE: str = "sqlite"  # Can be "sqlite" or "bigquery"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
