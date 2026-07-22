"""Filesystem layout for the model-input restore.

The reference directory name contains CJK characters whose on-disk Unicode
normalisation does not match a Python string literal on macOS, so every source
path is resolved by glob rather than by name.
"""
from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
REFERENCE = REPO / "reference"

OUT = REPO / "restored" / "model-input-2.32"
FACTOR_TREE_DIR = OUT / "factor-tree"
RAW_DIR = OUT / "raw"
CURATED_DIR = OUT / "curated"
QA_DIR = OUT / "qa"


def _glob_one(pattern: str, needle: str) -> Path:
    matches = [p for p in REFERENCE.glob(pattern) if needle in p.name]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected exactly one reference file matching {pattern!r} + {needle!r}, "
            f"found {[str(p) for p in matches]}"
        )
    return matches[0]


def source_workbook() -> Path:
    """The 2.32 model-input workbook being restored."""
    return _glob_one("*/*.xlsx", "model input_2.32")


def reference_workbook_224() -> Path:
    """The 2.24 dataset — the engine-taxonomy view of the same data."""
    return _glob_one("*/*.xlsx", "Data Process_2.24")


def mkdirs() -> None:
    for d in (OUT, FACTOR_TREE_DIR, RAW_DIR, CURATED_DIR, QA_DIR):
        d.mkdir(parents=True, exist_ok=True)
