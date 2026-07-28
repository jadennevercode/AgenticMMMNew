"""Run dbt commands and parse their artifacts into typed results.

This is the ONLY module that shells out to dbt and the ONLY one that reads dbt's
``target/*.json`` formats, so alpha-version format drift is contained here. Every
run deletes the stale ``run_results.json`` first, then reads the fresh one; if it
is missing (e.g. a parse error before any node ran) the failure is reconstructed
from the process output instead.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.dataeng.dbt.binary import resolve
from app.dataeng.dbt.workspace import Workspace

# dbt status strings, grouped by meaning.
_OK_STATUSES = {"success", "pass"}
_FAIL_STATUSES = {"error", "fail", "runtime error"}


@dataclass
class NodeResult:
    unique_id: str
    resource_type: str          # model | seed | test | source | snapshot
    name: str
    status: str                 # success | error | pass | fail | skipped
    execution_time: float = 0.0
    message: str = ""
    failures: int | None = None  # failing-row count for tests
    relation: str = ""           # "db"."schema"."name" for materialised nodes

    @property
    def ok(self) -> bool:
        return self.status in _OK_STATUSES


@dataclass
class DbtResult:
    ok: bool
    command: str
    returncode: int
    nodes: list[NodeResult] = field(default_factory=list)
    error: str = ""             # top-level failure summary (parse errors, crashes)
    stdout_tail: str = ""

    def by_type(self, resource_type: str) -> list[NodeResult]:
        return [n for n in self.nodes if n.resource_type == resource_type]

    @property
    def tests(self) -> list[NodeResult]:
        return self.by_type("test")

    @property
    def failed_nodes(self) -> list[NodeResult]:
        return [n for n in self.nodes if n.status in _FAIL_STATUSES]


def build(ws: Workspace, select: str | None = None,
          timeout: int | None = None) -> DbtResult:
    """`dbt build` — seed + run + test the selection (or the whole project)."""
    args = ["build"]
    if select:
        args += ["--select", select]
    return run(ws, args, timeout=timeout)


def parse(ws: Workspace, timeout: int | None = None) -> DbtResult:
    """`dbt parse` — validate project structure / model refs without executing."""
    return run(ws, ["parse"], timeout=timeout)


def run(ws: Workspace, args: list[str], timeout: int | None = None) -> DbtResult:
    """Invoke dbt in the workspace and parse the result. Never raises on dbt
    failure — a non-zero exit becomes ``DbtResult(ok=False, error=...)``."""
    info = resolve()
    ws.ensure()
    ws.clean_target()
    cmd = [info.path, *args, "--profiles-dir", str(ws.dir)]
    timeout = timeout or get_settings().dbt_timeout
    try:
        proc = subprocess.run(
            cmd, cwd=str(ws.dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return DbtResult(ok=False, command=" ".join(args), returncode=-1,
                         error=f"dbt timed out after {timeout}s")

    nodes = _read_run_results(ws.target_dir / "run_results.json")
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ok = proc.returncode == 0 and not any(
        n.status in _FAIL_STATUSES for n in nodes
    )
    error = "" if ok else _extract_error(combined, nodes)
    return DbtResult(
        ok=ok, command=" ".join(args), returncode=proc.returncode,
        nodes=nodes, error=error, stdout_tail=_tail(combined),
    )


def _read_run_results(path: Path) -> list[NodeResult]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[NodeResult] = []
    for r in data.get("results", []):
        uid = str(r.get("unique_id", ""))
        out.append(NodeResult(
            unique_id=uid,
            resource_type=uid.split(".", 1)[0] if uid else "",
            name=_readable_name(uid),
            status=str(r.get("status", "")),
            execution_time=float(r.get("execution_time") or 0.0),
            message=str(r.get("message") or ""),
            failures=r.get("failures"),
            relation=str(r.get("relation_name") or ""),
        ))
    return out


def _readable_name(uid: str) -> str:
    """Node name from a unique_id. Tests are ``test.<proj>.<name>.<hash>`` — drop
    the trailing hash; models/seeds are ``<type>.<proj>.<name>``."""
    parts = uid.split(".")
    if not uid:
        return ""
    if parts[0] == "test" and len(parts) >= 4:
        return parts[-2]
    return parts[-1]


def _extract_error(output: str, nodes: list[NodeResult]) -> str:
    """Prefer a concrete node failure; fall back to the first ``[error]`` line."""
    for n in nodes:
        if n.status in _FAIL_STATUSES:
            detail = n.message or f"{n.failures} failing rows"
            return f"{n.name}: {detail}"
    for line in output.splitlines():
        s = line.strip()
        if s.lower().startswith("[error]") or s.startswith("ERROR"):
            return s
    return _tail(output, lines=3).strip() or "dbt failed (see output)"


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])
