"""Configuration management using environment variables and Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application settings
    app_name: str = "LedgerLeaf"
    app_version: str = "0.2.0"
    app_env: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000

    # Paths and Storage
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    database_url: str = "sqlite:///./data/ledgerleaf.db"
    upload_dir: Path = Field(default_factory=lambda: Path("data/uploads"))
    max_upload_mb: int = 15
    allowed_extensions: List[str] = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"]

    # Security & CORS
    cors_origins: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "null",
    ]

    # AI Integration Settings (Local LM Studio / OpenAI-compatible server)
    ai_provider: str = "lm_studio"
    ai_base_url: str = "http://127.0.0.1:1234/v1"
    ai_model: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ai_model", "ai_model_name"),
    )
    ai_timeout_seconds: int = 120
    ai_max_retries: int = 1

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        """Ensure runtime directories for database and uploads exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    settings = Settings()
    settings.ensure_directories()
    return settings
