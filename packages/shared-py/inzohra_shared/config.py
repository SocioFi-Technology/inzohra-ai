"""Shared configuration. Read from environment / .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str

    # Redis
    redis_url: str

    # S3 / MinIO
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_raw: str = "inzohra-raw"
    s3_bucket_raster: str = "inzohra-raster"
    s3_bucket_crops: str = "inzohra-crops"
    s3_bucket_output: str = "inzohra-output"

    # LLM
    anthropic_api_key: str = ""
    model_primary: str = "claude-sonnet-4-5"
    model_escalation: str = "claude-opus-4-5"
    model_classifier: str = "claude-haiku-4-5-20251001"

    # App
    log_level: str = "INFO"
    opus_escalation_threshold: float = 0.70


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
