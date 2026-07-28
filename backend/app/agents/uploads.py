"""Human-upload handlers — render the 'provided' input artifacts.

These reflect what the user put in the Project Folder. S1 upload handlers list
the user's real files only (no Danone-reference fallback); the upstream upload
gate blocks until real files are present, and these handlers re-run on submit so
the artifact reflects exactly what was uploaded. (The S2 data intake is handled
by ``data.data_processing`` — it references Data Engine published assets.)
"""
from __future__ import annotations

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


