"""The project's target long-table schema.

Every published mart must emit these columns — they are the contract the modeling
engine (`model_df`) consumes. The default is seeded from reference/target-schema.xlsx
(a 22-column superset) reduced to the columns MMM actually models, with plain-English
definitions. It is editable per project (``ProjectState.target_schema``) and is used
to ground the AI's dbt codegen so generated marts land on the right shape.
"""
from __future__ import annotations

from app.domain.models import TargetColumn
from app.ingest.dataset import COLUMN_NAMES

# name → (label, definition, kind, required). Order follows COLUMN_NAMES (the 2.21
# modeling columns) so the emitted mart stays compatible with model_df.
_DEFAULT: dict[str, tuple[str, str, str, bool]] = {
    "task_name": ("Task", "Name of the source/task the row came from", "dimension", False),
    "brand": ("Brand", "Brand (model granularity)", "dimension", True),
    "province_group": ("Province group", "Province group / region (model granularity)", "dimension", False),
    "channel_type": ("Channel type", "Channel type, e.g. MT / TT / EC", "dimension", False),
    "channel": ("Channel", "Channel (detailed)", "dimension", False),
    "year": ("Year", "Year as an integer, e.g. 2023", "time", True),
    "month": ("Month", "Month as a yyyymm integer, e.g. 202301", "time", True),
    "source": ("Source", "Data-source tag (e.g. 'upload')", "dimension", False),
    "l1": ("Factor L1", "Factor tree Level 1", "factor", True),
    "l2": ("Factor L2", "Factor tree Level 2", "factor", True),
    "l3": ("Factor L3", "Factor tree Level 3", "factor", True),
    "l4": ("Factor L4", "Factor tree Level 4", "factor", True),
    "l5": ("Factor L5", "Drill-down Level 5 (empty if none)", "factor", False),
    "l6": ("Factor L6", "Drill-down Level 6 (empty if none)", "factor", False),
    "l7": ("Factor L7", "Drill-down Level 7 (empty if none)", "factor", False),
    "l8": ("Factor L8", "Drill-down Level 8 (empty if none)", "factor", False),
    "metric_type": ("Metric role", "Modeling role: Y (KPI/sell-out) | spending | X", "metric", True),
    "metric": ("Metric", "Indicator / metric name", "metric", True),
    "value": ("Value", "Numeric value (float)", "value", True),
}


def default_target_schema() -> list[TargetColumn]:
    cols: list[TargetColumn] = []
    for name in COLUMN_NAMES:
        label, definition, kind, required = _DEFAULT.get(
            name, (name.title(), "", "dimension", False))
        cols.append(TargetColumn(name=name, label=label, definition=definition,
                                 kind=kind, required=required))
    return cols


def schema_for(st) -> list[TargetColumn]:
    """The project's target schema, or the default if none has been customised."""
    return st.target_schema if st.target_schema else default_target_schema()


def columns_and_docs(st) -> tuple[list[str], dict[str, str]]:
    """(ordered column names, {name: definition}) to ground codegen."""
    schema = schema_for(st)
    docs = {c.name: (c.definition + (" [required]" if c.required else "")) for c in schema}
    return [c.name for c in schema], docs
