"""Public ingestion API for the Danone China MMM reference data.

Every loader reads the REAL reference files under ``reference/`` (no mock data).

    from app.ingest import load_model_dataset, load_factor_tree, summarize

Loaders:
    load_model_dataset()      -> pd.DataFrame  (long-format, ~23.8k rows)
    load_factor_tree()        -> dict          (L1->L4 hierarchy + indicators)
    load_validation_rules()   -> dict          (4-dimension scoring rubric)
    load_data_dictionary()    -> list[dict]    (per source-table metadata)
    load_scope()              -> dict
    load_kbqs()               -> list[dict]
    load_industry_knowledge() -> dict
    load_interviews()         -> list[dict]    (full transcript per docx)
    summarize()               -> dict          (counts of everything)
"""
from __future__ import annotations

from .business import load_industry_knowledge, load_kbqs, load_scope
from .data_dictionary import load_data_dictionary
from .dataset import load_model_dataset
from .factor_tree import load_factor_tree
from .interviews import load_interviews
from .reference import summarize
from .validation import load_validation_rules

__all__ = [
    "load_model_dataset",
    "load_factor_tree",
    "load_validation_rules",
    "load_data_dictionary",
    "load_scope",
    "load_kbqs",
    "load_industry_knowledge",
    "load_interviews",
    "summarize",
]
