"""Per-project file folder — real upload + storage + parse for source materials.

Files live on disk under ``data/projects/{id}/files/{category}/{filename}`` with a
metadata index at ``data/projects/{id}/files/_index.json``. On upload each file is
extracted (text + tables via app.ingest.extract) so downstream agents can ground
on the user's *actual* materials rather than the fixed Danone reference set.

S1 agents ground strictly on parsed project files for their category (see
app.agents.sources) — there is no Danone-reference fallback, and the S1 upload
gates block until real files are present.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.domain.models import FileCategory, ProjectFile
from app.ingest.extract import extract_document, is_audio_filename

_CATEGORIES: tuple[FileCategory, ...] = (
    "project_background", "industry_reference", "interview_minutes",
    "factor_tree", "data", "raw_data", "other",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(filename: str) -> str:
    """Strip path components and dangerous characters from an uploaded name."""
    base = Path(filename).name
    cleaned = re.sub(r"[^\w.\-() 一-鿿]", "_", base).strip()
    return cleaned or "upload"


class ProjectFiles:
    """Disk-backed store of one project's uploaded files, with a JSON index."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def _root(self, project_id: str) -> Path:
        return get_settings().data_path / "projects" / project_id / "files"

    def _index_path(self, project_id: str) -> Path:
        return self._root(project_id) / "_index.json"

    def _read_index(self, project_id: str) -> list[ProjectFile]:
        path = self._index_path(project_id)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [ProjectFile.model_validate(r) for r in raw]
        except (json.JSONDecodeError, ValueError):
            return []

    def _write_index(self, project_id: str, files: list[ProjectFile]) -> None:
        root = self._root(project_id)
        root.mkdir(parents=True, exist_ok=True)
        self._index_path(project_id).write_text(
            json.dumps([f.model_dump(by_alias=True) for f in files], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── public API ───────────────────────────────────────
    def list(self, project_id: str) -> list[ProjectFile]:
        with self._lock:
            return self._read_index(project_id)

    def add(self, project_id: str, category: FileCategory, filename: str,
            content: bytes, content_type: str = "", slot: Optional[str] = None) -> ProjectFile:
        if category not in _CATEGORIES:
            raise ValueError(f"unknown file category: {category}")
        with self._lock:
            file_id = uuid.uuid4().hex[:12]
            safe = _safe_name(filename)
            cat_dir = self._root(project_id) / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            # Disambiguate on disk with the file id to avoid collisions.
            disk_path = cat_dir / f"{file_id}__{safe}"
            disk_path.write_bytes(content)

            result = extract_document(disk_path)
            # A data-request slot can hold only one workbook — drop any prior file
            # bound to the same slot so re-upload replaces it.
            existing = self._read_index(project_id)
            if slot:
                for f in existing:
                    if f.category == "data" and f.slot == slot:
                        self._delete_disk(project_id, f)
                existing = [f for f in existing if not (f.category == "data" and f.slot == slot)]

            # Audio interview uploads aren't parsed at upload — they await the ASR
            # step (task 1.4b), which writes a .txt transcript sidecar.
            asr_status = "pending" if is_audio_filename(safe) else ""
            record = ProjectFile(
                id=file_id, category=category, filename=safe, size=len(content),
                contentType=content_type, uploadedAt=_now_iso(),
                parsed=result.ok, parseChars=len(result.text), parseError=result.error,
                slot=slot, asrStatus=asr_status,
            )
            files = [f for f in existing if f.id != file_id]
            files.append(record)
            self._write_index(project_id, files)
            return record

    def update_record(self, project_id: str, file_id: str, **fields) -> Optional[ProjectFile]:
        """Patch fields on an indexed file record (e.g. asr_status). Returns the
        updated record, or None if the file id isn't found."""
        with self._lock:
            files = self._read_index(project_id)
            updated: Optional[ProjectFile] = None
            for i, f in enumerate(files):
                if f.id == file_id:
                    updated = f.model_copy(update=fields)
                    files[i] = updated
                    break
            if updated is not None:
                self._write_index(project_id, files)
            return updated

    def audio_pending(self, project_id: str, category: FileCategory) -> list[ProjectFile]:
        """Audio files in a category that still need transcription."""
        with self._lock:
            return [f for f in self._read_index(project_id)
                    if f.category == category and is_audio_filename(f.filename)
                    and f.asr_status in ("", "pending", "error")]

    def _delete_disk(self, project_id: str, record: ProjectFile) -> None:
        disk = self._root(project_id) / record.category / f"{record.id}__{record.filename}"
        if disk.exists():
            disk.unlink()

    def get_path(self, project_id: str, file_id: str) -> Optional[tuple[ProjectFile, Path]]:
        with self._lock:
            record = next((f for f in self._read_index(project_id) if f.id == file_id), None)
            if record is None:
                return None
            disk = self._root(project_id) / record.category / f"{file_id}__{record.filename}"
            return (record, disk) if disk.exists() else None

    def delete(self, project_id: str, file_id: str) -> bool:
        with self._lock:
            files = self._read_index(project_id)
            record = next((f for f in files if f.id == file_id), None)
            if record is None:
                return False
            disk = self._root(project_id) / record.category / f"{file_id}__{record.filename}"
            if disk.exists():
                disk.unlink()
            self._write_index(project_id, [f for f in files if f.id != file_id])
            return True

    def extract_category_text(self, project_id: str, category: FileCategory,
                              max_chars: int = 9000) -> str:
        """Concatenate extracted text from all parsed files in a category.

        Returns "" when the category is empty; S1 callers treat that as a blocked
        deliverable (no reference fallback).
        """
        with self._lock:
            records = [f for f in self._read_index(project_id)
                       if f.category == category and f.parsed]
            if not records:
                return ""
            parts: list[str] = []
            for rec in records:
                found = self.get_path(project_id, rec.id)
                if found is None:
                    continue
                result = extract_document(found[1])
                if result.text:
                    parts.append(f"### {rec.filename}\n{result.text}")
            return "\n\n".join(parts)[:max_chars]

    def has_category(self, project_id: str, category: FileCategory) -> bool:
        # An audio interview upload satisfies the upload gate even before it's
        # transcribed — the ASR step (1.4b) runs after the gate clears.
        with self._lock:
            return any(f.category == category and (f.parsed or is_audio_filename(f.filename))
                       for f in self._read_index(project_id))

    def purge(self, project_id: str) -> None:
        """Remove the whole project folder (called when a project is deleted)."""
        import shutil

        with self._lock:
            project_dir = get_settings().data_path / "projects" / project_id
            if project_dir.exists():
                shutil.rmtree(project_dir, ignore_errors=True)


_files: Optional[ProjectFiles] = None


def get_files() -> ProjectFiles:
    global _files
    if _files is None:
        _files = ProjectFiles()
    return _files
