"""Global model-service configuration store.

A single GlobalModelConfig for ALL projects — the LLM + ASR credentials the user
enters once in Settings (real API key, base URL, model name). Persisted to
`data/model_service.json` (gitignored). This replaces the old per-project
ProjectModelConfig + env-var key-ref indirection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.domain.models import GlobalModelConfig

_CACHE: Optional[GlobalModelConfig] = None


def _config_path() -> Path:
    return get_settings().data_path / "model_service.json"


def get_model_service() -> GlobalModelConfig:
    """Return the global model config, loading it from disk once and caching.

    A missing or malformed file yields an empty config (unconfigured) rather than
    crashing — the LLM run-gate then blocks until the user fills Settings."""
    global _CACHE
    if _CACHE is None:
        path = _config_path()
        try:
            _CACHE = GlobalModelConfig.model_validate_json(path.read_text("utf-8"))
        except (OSError, ValueError):
            _CACHE = GlobalModelConfig()
    return _CACHE


def save_model_service(cfg: GlobalModelConfig) -> GlobalModelConfig:
    """Persist the global model config and refresh the in-process cache."""
    global _CACHE
    _config_path().write_text(cfg.model_dump_json(by_alias=True, indent=2), "utf-8")
    _CACHE = cfg
    return cfg
