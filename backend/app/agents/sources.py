"""Grounding-source resolution for S1 — user uploads ONLY.

Every S1 agent that grounds on "materials the user provided" routes through
here. S1 deliverables are parsed strictly from the project's *real uploaded*
files in the relevant Project-Folder category; there is no Danone-reference
fallback. Upstream upload gates (1.0a / 1.1a / 1.4a) block until real files are
present, so by the time a producing S1 handler runs the category is non-empty.
"""
from __future__ import annotations

from app.domain.models import FileCategory
from app.store.files import get_files


def category_text(project_id: str, category: FileCategory, max_chars: int = 9000) -> str:
    """Extracted text from a project-folder category, or "" if empty."""
    return get_files().extract_category_text(project_id, category, max_chars=max_chars)


def has_uploads(project_id: str, category: FileCategory) -> bool:
    return get_files().has_category(project_id, category)
