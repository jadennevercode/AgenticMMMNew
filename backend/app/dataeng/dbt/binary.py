"""Locate and validate the pinned dbt Fusion binary.

dbt Core v2.0 (Fusion) ships as a single self-contained binary with the DuckDB
adapter built in — no Python runtime, no separate ADBC driver. We pin a known-good
version because v2.0 is still ``preview`` (alpha) and its on-disk artifact formats
may shift between builds.

Install (macOS arm64 example — do NOT pipe the remote installer to a shell):

    curl -fsSL https://public.cdn.getdbt.com/fs/cli/fs-v2.0.0-preview.199-aarch64-apple-darwin.tar.gz \\
      | tar -xz -C /tmp && install -m755 /tmp/dbt ~/.local/bin/dbt

Detection order: ``DBT_BIN`` env / ``settings.dbt_bin`` → ``~/.local/bin/dbt`` → PATH.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

# The version this integration was built and tested against. A different installed
# version still runs, but we surface a warning so artifact-format drift is visible.
PINNED_VERSION = "2.0.0-preview.199"


class DbtBinaryError(RuntimeError):
    """Raised when no usable dbt binary can be found."""


def _candidates() -> list[str]:
    out: list[str] = []
    configured = (get_settings().dbt_bin or "").strip()
    if configured:
        out.append(configured)
    out.append(str(Path.home() / ".local" / "bin" / "dbt"))
    found = shutil.which("dbt")
    if found:
        out.append(found)
    return out


@dataclass(frozen=True)
class DbtInfo:
    path: str
    version: str
    version_matches: bool


@lru_cache
def resolve() -> DbtInfo:
    """Return the resolved dbt binary + its version, or raise ``DbtBinaryError``."""
    tried: list[str] = []
    for cand in _candidates():
        p = Path(cand)
        if not (p.exists() and p.is_file()):
            tried.append(f"{cand} (missing)")
            continue
        version = _probe_version(cand)
        if version is None:
            tried.append(f"{cand} (not runnable)")
            continue
        return DbtInfo(path=cand, version=version, version_matches=version == PINNED_VERSION)
    raise DbtBinaryError(
        "dbt Fusion binary not found. Install it and/or set DBT_BIN. Tried: "
        + "; ".join(tried or ["<no candidates>"])
    )


def _probe_version(path: str) -> str | None:
    try:
        out = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or "") + (out.stderr or "")
    # e.g. "dbt-fusion 2.0.0-preview.199"
    for token in text.split():
        if token[:1].isdigit():
            return token.strip()
    return None


def available() -> tuple[bool, str]:
    """Non-raising probe for health checks / API preconditions."""
    try:
        info = resolve()
    except DbtBinaryError as e:
        return False, str(e)
    note = "" if info.version_matches else f" (pinned {PINNED_VERSION})"
    return True, f"dbt {info.version} at {info.path}{note}"
