"""Application settings loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM / ASR operational knobs. The actual credentials (key, base-url, model)
    # are NOT read from env anymore — they live in the global model-service config
    # the user fills once in Settings (see app/store/model_service.py).
    llm_timeout: int = 120
    llm_max_retries: int = 3
    asr_timeout: int = 600

    # Storage / data
    data_dir: str = "./data"
    db_path: str = "./data/mmm.db"
    reference_dir: str = "../reference"

    @property
    def data_path(self) -> Path:
        p = (BACKEND_ROOT / self.data_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_file(self) -> Path:
        return (BACKEND_ROOT / self.db_path).resolve()

    @property
    def reference_path(self) -> Path:
        return (BACKEND_ROOT / self.reference_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
