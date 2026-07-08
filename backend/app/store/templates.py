"""Knowledge-template store — editable, per-industry factor-tree & interview templates.

Templates are reusable across projects and keyed by industry (codes from
domain/industries.py). Built-in beverage templates are seeded from the Assets
workbooks on first access; users can clone, edit rows, and create new-industry
templates. Persisted as a single JSON file at data/templates/_index.json.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.domain.models import KnowledgeTemplate, TemplateKind
from app.store.template_seed import build_builtin_templates


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TemplateStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._initialized = False

    def _path(self) -> Path:
        root = get_settings().data_path / "templates"
        root.mkdir(parents=True, exist_ok=True)
        return root / "_index.json"

    def _read(self) -> list[KnowledgeTemplate]:
        path = self._path()
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [KnowledgeTemplate.model_validate(t) for t in raw]
        except (json.JSONDecodeError, ValueError):
            return []

    def _write(self, templates: list[KnowledgeTemplate]) -> None:
        self._path().write_text(
            json.dumps([t.model_dump(by_alias=True) for t in templates], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_seeded(self) -> None:
        if self._initialized:
            return
        if not self._path().exists():
            self._write(build_builtin_templates())
        else:
            # Heal older installs: back-fill any built-in section added since the
            # index was first written (e.g. rules / industry / general knowledge).
            items = self._read()
            have = {t.id for t in items}
            missing = [t for t in build_builtin_templates() if t.id not in have]
            if missing:
                self._write(items + missing)
        self._initialized = True

    # ── public API ───────────────────────────────────────
    def list(self, kind: Optional[TemplateKind] = None,
             industry_l1: Optional[str] = None) -> list[KnowledgeTemplate]:
        with self._lock:
            self._ensure_seeded()
            items = self._read()
            if kind:
                items = [t for t in items if t.kind == kind]
            if industry_l1:
                items = [t for t in items if t.industry_l1 == industry_l1]
            return items

    def get(self, template_id: str) -> Optional[KnowledgeTemplate]:
        with self._lock:
            self._ensure_seeded()
            return next((t for t in self._read() if t.id == template_id), None)

    def best_match(self, kind: TemplateKind, l1: str, l2: Optional[str] = None) -> Optional[KnowledgeTemplate]:
        """Find the most specific template for an industry (l2 match beats l1-only)."""
        with self._lock:
            self._ensure_seeded()
            items = [t for t in self._read() if t.kind == kind]
            l2_match = [t for t in items if t.industry_l1 == l1 and l2 and t.industry_l2 == l2]
            if l2_match:
                return l2_match[0]
            l1_match = [t for t in items if t.industry_l1 == l1]
            return l1_match[0] if l1_match else None

    def general(self) -> Optional[KnowledgeTemplate]:
        """The cross-industry general-knowledge section (first match), if any."""
        with self._lock:
            self._ensure_seeded()
            return next((t for t in self._read() if t.kind == "general_knowledge"), None)

    def save(self, template: KnowledgeTemplate) -> KnowledgeTemplate:
        with self._lock:
            self._ensure_seeded()
            items = self._read()
            template.updated_at = _now_iso()
            existing = next((t for t in items if t.id == template.id), None)
            if existing is not None:
                template.version = existing.version + 1
                items = [t if t.id != template.id else template for t in items]
            else:
                if not template.id:
                    template.id = f"tpl-{uuid.uuid4().hex[:10]}"
                items.append(template)
            self._write(items)
            return template

    def clone(self, template_id: str, name: Optional[str] = None) -> Optional[KnowledgeTemplate]:
        with self._lock:
            src = self.get(template_id)
            if src is None:
                return None
            copy = src.model_copy(deep=True)
            copy.id = f"tpl-{uuid.uuid4().hex[:10]}"
            copy.name = name or f"{src.name} (copy)"
            copy.builtin = False
            copy.version = 1
            copy.updated_at = _now_iso()
            items = self._read()
            items.append(copy)
            self._write(items)
            return copy

    def delete(self, template_id: str) -> bool:
        with self._lock:
            self._ensure_seeded()
            items = self._read()
            target = next((t for t in items if t.id == template_id), None)
            if target is None or target.builtin:
                return False
            self._write([t for t in items if t.id != template_id])
            return True


_templates: Optional[TemplateStore] = None


def get_templates() -> TemplateStore:
    global _templates
    if _templates is None:
        _templates = TemplateStore()
    return _templates
