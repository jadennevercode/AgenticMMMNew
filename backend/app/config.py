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
    # Minimum seconds between LLM requests once the endpoint has answered with a
    # rate-limit error. Zero pacing is applied until that happens, so endpoints
    # without a quota run at full speed. 7s ≈ 17 requests/2min, just under the
    # 20/2min ceiling the current gateway enforces (it answers a burst with a
    # 10-minute lockout, which silently empties every grounded agent step).
    llm_paced_interval: float = 7.0
    asr_timeout: int = 600

    # How much grounding material one agent call may see (characters). This used
    # to be a dozen independently-chosen constants applied silently, so a 200-page
    # deck and its first six thousand characters produced indistinguishable
    # deliverables. Handlers that still have to clip now say so (see
    # agents.common.truncation_finding).
    grounding_max_chars: int = 100_000

    # Storage / data
    data_dir: str = "./data"
    db_path: str = "./data/mmm.db"
    reference_dir: str = "../reference"
    # The Danone reference dataset stands in for a project's own data only for the
    # seeded demo. Set this to run any project against the reference table (local
    # debugging) — in normal operation a project without usable data must BLOCK,
    # not silently score someone else's numbers.
    allow_reference_fallback: bool = False

    # dbt Fusion engine (Data Engine transform layer). Empty ⇒ auto-detect the
    # binary (env DBT_BIN, then ~/.local/bin/dbt, then PATH). See app/dataeng/dbt.
    dbt_bin: str = ""
    dbt_timeout: int = 300

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
