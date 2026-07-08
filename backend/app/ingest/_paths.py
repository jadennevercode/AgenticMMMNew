"""Shared filesystem helpers for the reference-data ingestion layer.

All reference files live under ``reference/`` (sibling of ``backend/``).
We resolve them via the app settings so the layer works regardless of the
caller's current working directory.
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings

# Sub-folders inside the reference root.
BIZ = "01.商业智能体"
DATA = "02.数据智能体"
REPORT = "04.报告智能体"

# Concrete reference files (verified to exist).
MODEL_DATASET = f"{DATA}/【MMM AI】数据智能体-Data Process_2.24.xlsx"
MODEL_DATASET_SHEET = "dataset_model_data_yyyymm_20260"

FACTOR_TREE = f"{DATA}/【MMM AI】商业智能体-因子树+下钻维度+交叉检验_2.31.xlsx"
FACTOR_TREE_SHEET = "下钻因子树"

VALIDATION = f"{DATA}/【MMM AI】数据智能体-Data Validation_2.1.xlsx"
DATA_DICT = f"{DATA}/【MMM AI】数据智能体-Data Process_2.21&2.23.xlsm"
DATA_DICT_SHEET = "数据字典"

SCOPE = f"{BIZ}/【MMM AI】商业智能体-Scope.xlsx"
KBQS = f"{BIZ}/【MMM AI】商业智能体-KBQs.xlsx"
INDUSTRY = f"{BIZ}/【MMM AI】商业智能体-行业知识.xlsx"
INTERVIEW_DIR = f"{BIZ}/【MMM AI】商业智能提-访谈框架及纪要/纪要"


def reference_root() -> Path:
    """Absolute path to the reference data root."""
    return get_settings().reference_path


def _skip(name: str) -> bool:
    """Ignore Office temp files and archive folders when matching."""
    return name.startswith("~$") or name.startswith("[") or name.startswith(".")


def _best_match(parent: Path, segment: str) -> Path | None:
    """Find the file/dir in `parent` matching `segment`, tolerating version
    suffixes (e.g. ``…-Scope.xlsx`` → ``…-Scope_1.0.xlsx``). Newest wins."""
    if not parent.is_dir():
        return None
    stem, ext = (segment.rsplit(".", 1) + [""])[:2] if "." in segment else (segment, "")
    want_ext = f".{ext}".lower() if ext else ""
    candidates: list[Path] = []
    for child in parent.iterdir():
        if _skip(child.name):
            continue
        if want_ext:  # matching a file
            if child.is_file() and child.suffix.lower() == want_ext and child.stem.startswith(stem):
                candidates.append(child)
        else:  # matching a directory
            if child.is_dir() and child.name.startswith(stem):
                candidates.append(child)
    if not candidates:
        return None
    # Prefer the longest name (most specific / highest version), then lexical max.
    return sorted(candidates, key=lambda p: (len(p.name), p.name))[-1]


def ref(relative: str) -> Path:
    """Resolve a reference path, tolerating version-suffixed file/dir names.

    Each path segment is matched exactly first, then by a version-tolerant glob
    (so ``…-Scope.xlsx`` resolves to ``…-Scope_1.0.xlsx`` and an interview
    directory ``…纪要`` resolves under ``…访谈框架及纪要_1.32``).
    """
    p = reference_root()
    for segment in Path(relative).parts:
        exact = p / segment
        if exact.exists():
            p = exact
            continue
        match = _best_match(p, segment)
        if match is None:
            raise FileNotFoundError(
                f"Reference file not found: {p / segment} (no version-tolerant match)")
        p = match
    return p
