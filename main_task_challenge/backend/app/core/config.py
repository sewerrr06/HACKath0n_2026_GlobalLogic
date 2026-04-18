from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "INS Challenge Backend"
    app_env: str = "dev"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/ins_challenge"
    logs_dir: Path = Path("/data/logs")
    uploads_dir: Path = Path("/data/inputs")
    outputs_dir: Path = Path("/data/outputs")
    fusion_algorithm: str = "ekf"
    gps_instance: int = 0
    min_gps_status: int = 1
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
