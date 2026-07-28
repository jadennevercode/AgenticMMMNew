"""The 2.1 Data Intake gate — one authority, one answer.

The gate used to be judged twice with different rules: the backend asked
"is the FactorTree↔DataAssets mapping resolved (or the legacy manifest valid)?"
while the frontend asked "are there parsed files in the Project-Folder `data`
category?". A project that resolved every factor row in the Data Engine
therefore satisfied the server and stayed blocked in the UI forever.

This module is the single judge. It returns not just a boolean but *why*, so the
UI can render the real blockers instead of a hardcoded "upload a file" message,
and so the gate can also refuse the cases that used to slip through: a factor
tree with no rows, an unreadable manifest, or data that carries no modelable
taxonomy at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.store.state import ProjectState


@dataclass(frozen=True)
class DataIntakeStatus:
    """Whether the 2.1 gate may be submitted, and what is missing if not."""
    ready: bool = False
    path: str = "none"          # "mapping" | "manifest" | "upload" | "none"
    total: int = 0
    mapped: int = 0
    ignored: int = 0
    pending: int = 0
    blockers: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "ready": self.ready, "path": self.path, "total": self.total,
            "mapped": self.mapped, "ignored": self.ignored, "pending": self.pending,
            "blockers": list(self.blockers),
        }


def _mapping_status(st: ProjectState) -> tuple[bool, dict, list[str]]:
    """(complete, counts, blockers) for the Data-Engine mapping path."""
    try:
        from app.dataeng.mapping import resolve_factor_map
        fmap = resolve_factor_map(st)
    except Exception as exc:  # noqa: BLE001 — a mapping error blocks, loudly.
        return False, {}, [f"The factor map could not be resolved: {exc}"]
    counts = {"total": fmap.total, "mapped": fmap.mapped,
              "ignored": fmap.ignored, "pending": fmap.pending}
    if fmap.total == 0:
        return False, counts, ["The factor tree has no active rows to map. "
                               "Complete Business Understanding (1.21) first."]
    if fmap.pending:
        return False, counts, [
            f"{fmap.pending} of {fmap.total} factor rows are still unresolved. "
            f"In the Data Engine, bind each one to a published indicator or mark it ignored."
        ]
    return True, counts, []


def _manifest_status(st: ProjectState) -> tuple[bool, list[str]]:
    """(satisfied, blockers) for the legacy per-L3 slot-upload path."""
    try:
        from app.agents.data_request import build_manifest
        m = build_manifest(st)
    except Exception as exc:  # noqa: BLE001 — an unreadable manifest blocks; it
        return False, [f"The data-request manifest could not be built: {exc}"]  # used to pass.
    if m.total == 0:
        return False, ["The data request has no L3 slots to satisfy."]
    if m.validated < m.total:
        missing = [s.l3 for s in m.slots if s.status != "validated"]
        return False, [f"{m.total - m.validated} of {m.total} L3 workbooks are not validated: "
                       + ", ".join(missing[:6]) + ("…" if len(missing) > 6 else "")]
    return True, []


def _data_blockers(st: ProjectState) -> list[str]:
    """Blockers from the data itself: no usable table, or no modelable taxonomy.

    Checked at the gate rather than five steps later, because a table with no Y
    (or no `channel_type`) lets every S2 task report success over an empty
    universe — the failure only surfaces at 2.6, as "0 objects".
    """
    from app.agents.dataset_cache import dataset_blocker, diagnose_taxonomy
    blocked = dataset_blocker(st)
    if blocked:
        return [blocked]
    return list(diagnose_taxonomy(st).problems)


def intake_status(st: ProjectState, asg: dict) -> DataIntakeStatus:
    """Judge the 2.1 gate. A gate carrying only one flag is judged only by it."""
    blockers: list[str] = []
    counts: dict = {}
    path = "none"
    ready = False

    if asg.get("requiresMapping"):
        ok, counts, why = _mapping_status(st)
        if ok:
            ready, path = True, "mapping"
        else:
            blockers += why

    if not ready and asg.get("requiresManifest"):
        ok, why = _manifest_status(st)
        if ok:
            ready, path = True, "manifest"
        else:
            blockers += why

    if not (asg.get("requiresMapping") or asg.get("requiresManifest")):
        # Plain upload gate — file presence is the whole rule.
        from app.store.files import get_files
        category = asg.get("category")
        if category and get_files().has_category(st.project_id, category):
            ready, path = True, "upload"
        else:
            blockers.append("Upload at least one readable file to continue.")

    # Even a fully mapped project must have data that can actually be modelled.
    if ready:
        data_why = _data_blockers(st)
        if data_why:
            ready = False
            blockers += data_why

    return DataIntakeStatus(
        ready=ready, path=path if ready else "none",
        total=int(counts.get("total", 0)), mapped=int(counts.get("mapped", 0)),
        ignored=int(counts.get("ignored", 0)), pending=int(counts.get("pending", 0)),
        blockers=blockers,
    )
