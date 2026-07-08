"""Human-upload handlers — render the 'provided' input artifacts.

These reflect what the user put in the Project Folder. S1 upload handlers list
the user's real files only (no Danone-reference fallback); the upstream upload
gate blocks until real files are present, and these handlers re-run on submit so
the artifact reflects exactly what was uploaded. (The S2 data handler still
summarizes the reference data dictionary when no data files are uploaded, since
the quantitative engine runs on the single reference dataset.)
"""
from __future__ import annotations

from app import ingest
from app.domain.models import FileCategory
from app.orchestrator.engine import Engine
from app.store.files import get_files
from app.store.state import ProjectState


def _uploaded_blocks(project_id: str, category: FileCategory) -> list[dict]:
    """Doc blocks listing the user's uploaded files for a category (or [])."""
    files = [f for f in get_files().list(project_id) if f.category == category]
    if not files:
        return []
    blocks = [{"type": "li", "text": f"{f.filename} ({f.size // 1024 or 1} KB · "
               f"{'parsed' if f.parsed else 'not parsed'})"} for f in files]
    return blocks


async def provide_sow(eng: Engine, st: ProjectState, task: dict) -> None:
    blocks = [
        {"type": "h1", "text": "SOW & Brief (provided)"},
        {"type": "h2", "text": "Uploaded files"},
    ]
    uploaded = _uploaded_blocks(st.project_id, "project_background")
    if uploaded:
        blocks.extend(uploaded)
    else:
        blocks.append({"type": "p", "text": "No SOW/brief uploaded yet — add the signed SOW and kickoff "
                       "brief to the Project Folder (Project Background), then submit."})
    eng.produce(st, "a-sow", body={"blocks": blocks}, state="confirmed", agent="business")


async def provide_materials(eng: Engine, st: ProjectState, task: dict) -> None:
    blocks = [
        {"type": "h1", "text": "Reports & Materials (provided)"},
        {"type": "h2", "text": "Uploaded files"},
    ]
    uploaded = _uploaded_blocks(st.project_id, "industry_reference")
    if uploaded:
        blocks.extend(uploaded)
    else:
        blocks.append({"type": "p", "text": "No industry materials uploaded yet — add brand & competitor "
                       "reports to the Project Folder (Industry Reference), then submit."})
    eng.produce(st, "a-source-materials", body={"blocks": blocks}, state="confirmed", agent="business")


async def provide_data_files(eng: Engine, st: ProjectState, task: dict) -> None:
    uploaded = [f for f in get_files().list(st.project_id) if f.category == "data"]
    if uploaded:
        rows = [[f.filename, str(f.size // 1024 or 1) + " KB",
                 "parsed" if f.parsed else "not parsed"] for f in uploaded]
        body = {"sheets": [{"name": "Uploaded data files",
                            "columns": ["File", "Size", "Parse"], "rows": rows}]}
        eng.produce(st, "a-data-files", body=body, state="confirmed", agent="data")
        eng.emit(st, "data", "info", f"{len(uploaded)} data files catalogued from the Project Folder", task["id"])
        return
    # Fallback: summarize the real returned data sources from the data dictionary.
    rows = []
    try:
        dd = ingest.load_data_dictionary()
        seen = set()
        for r in dd:
            sysn = str(r.get("source_system") or r.get("source_dept") or "—")
            tbl = str(r.get("table_name") or r.get("sheet") or "")
            if not tbl or (sysn, tbl) in seen:
                continue
            seen.add((sysn, tbl))
            rows.append([sysn, tbl, str(r.get("granularity") or ""), str(r.get("y_or_x") or "")])
    except Exception:  # noqa: BLE001
        rows = [["—", "(reference unavailable)", "", ""]]
    body = {"sheets": [{"name": "回填清单 (returned data sources)",
                        "columns": ["来源系统", "表/Sheet", "颗粒度", "Y/X"], "rows": rows[:60]}]}
    eng.produce(st, "a-data-files", body=body, state="confirmed", agent="data")
    eng.emit(st, "data", "info", f"{len(rows)} data sources catalogued", task["id"])
