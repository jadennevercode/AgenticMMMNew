"""The on-disk dbt project for one MMM project.

Disk is the source of truth for the dbt files. This module scaffolds the project,
pre-loads raw uploads into the warehouse's ``raw`` schema (exposed to dbt via
``sources.yml``), and reads/writes the model / seed / schema files. It never runs
dbt itself — that is ``executor.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from app.config import get_settings
from app.dataeng.duck import sanitize_ident

# Fixed identifiers inside a workspace. The project name only needs to be a valid
# dbt identifier and never collides across projects (one workspace dir each).
PROFILE_NAME = "mmm"
PROJECT_NAME = "mmm"
RAW_SCHEMA = "raw"
MODEL_SCHEMA = "main"  # dbt's default target schema for materialised models
LAYERS = ("staging", "intermediate", "marts")

_DBT_PROJECT_YML = f"""\
name: {PROJECT_NAME}
version: '1.0.0'
profile: {PROFILE_NAME}
model-paths: ["models"]
seed-paths: ["seeds"]
macro-paths: ["macros"]
target-path: "target"
clean-targets: ["target"]
"""

# MMM data-quality generic tests, written into every workspace's macros/ so schema.yml
# can attach them. Each {% test %} returns FAILING rows (>0 rows ⇒ test fails). The
# time-based tests key on a DATE column (the MMM period axis). See docs/ for rationale:
#   1. time_span_min_years  — coverage must exceed N years (default 2) to fit seasonality
#   2. time_granularity_allowed — daily/weekly/monthly only; reject yearly/coarser
#   3. has_variation        — a driver with no variance can't identify an OLS coefficient
#   4. yoy_comparable       — per-year period counts must be consistent (years comparable)
_MMM_GENERIC_TESTS = """\
{% test time_span_min_years(model, column_name, min_years=2) %}
-- Fail when the time span (first→last period) covers fewer than min_years years.
-- Measured in inclusive months so a clean 2-year monthly series (24 points) passes.
select 1 as failure
from (
    select min({{ column_name }}) as mn, max({{ column_name }}) as mx
    from {{ model }}
    where {{ column_name }} is not null
) s
where s.mn is null
   or (date_diff('month', s.mn, s.mx) + 1) < ({{ min_years }} * 12)
{% endtest %}


{% test time_granularity_allowed(model, column_name, max_gap_days=45) %}
-- Fail when the typical spacing between consecutive periods is coarser than monthly
-- (i.e. quarterly/yearly), or when there is only one period (granularity undefined).
-- daily≈1d, weekly≈7d, monthly≈28-31d all pass under the default 45-day ceiling.
with d as (
    select distinct {{ column_name }} as dt from {{ model }} where {{ column_name }} is not null
),
g as (
    select date_diff('day', lag(dt) over (order by dt), dt) as gap from d
)
select 1 as failure
from (select median(gap) as mg, count(gap) as n from g) s
where s.n = 0 or s.mg > {{ max_gap_days }}
{% endtest %}


{% test has_variation(model, column_name, min_cv=0) %}
-- Fail when the column is (near-)constant: OLS cannot estimate a coefficient for a
-- driver that does not move. Optionally require a minimum coefficient of variation.
select 1 as failure
from (
    select stddev_pop({{ column_name }}) as sd,
           avg({{ column_name }}) as mu,
           count(distinct {{ column_name }}) as nd
    from {{ model }}
    where {{ column_name }} is not null
) s
where s.nd <= 1 or s.sd is null or s.sd = 0
   {% if min_cv and min_cv > 0 %} or (abs(s.mu) > 0 and (s.sd / abs(s.mu)) < {{ min_cv }}) {% endif %}
{% endtest %}


{% test yoy_comparable(model, column_name, tolerance=0.5) %}
-- Fail when years are not comparable: some year has far fewer periods than the best-
-- covered year (a partial/inconsistent year breaks year-over-year comparison). Keyed
-- on the DATE period column; tolerance is the min acceptable coverage ratio.
with per_year as (
    select extract(year from {{ column_name }}) as yr,
           count(distinct {{ column_name }}) as cnt
    from {{ model }}
    where {{ column_name }} is not null
    group by 1
)
select 1 as failure
from (select min(cnt) as mn, max(cnt) as mx, count(*) as ny from per_year) s
where s.ny >= 2 and s.mn < ({{ tolerance }} * s.mx)
{% endtest %}
"""


def _profiles_yml(warehouse: Path) -> str:
    return (
        f"{PROFILE_NAME}:\n"
        f"  target: dev\n"
        f"  outputs:\n"
        f"    dev:\n"
        f"      type: duckdb\n"
        f"      path: {warehouse}\n"
        f"      threads: 1\n"
    )


@dataclass(frozen=True)
class ModelFile:
    layer: str          # one of LAYERS
    name: str           # model name = file stem = relation name
    sql: str


class Workspace:
    """Filesystem handle to a project's dbt project (does not run dbt)."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.dir = get_settings().data_path / "projects" / project_id / "dbt"

    # ── paths ────────────────────────────────────────────
    @property
    def models_dir(self) -> Path:
        return self.dir / "models"

    @property
    def seeds_dir(self) -> Path:
        return self.dir / "seeds"

    @property
    def macros_dir(self) -> Path:
        return self.dir / "macros"

    @property
    def target_dir(self) -> Path:
        return self.dir / "target"

    @property
    def warehouse_path(self) -> Path:
        return self.dir / "warehouse.duckdb"

    def model_path(self, layer: str, name: str) -> Path:
        return self.models_dir / layer / f"{sanitize_ident(name)}.sql"

    def seed_path(self, name: str) -> Path:
        return self.seeds_dir / f"{sanitize_ident(name)}.csv"

    # ── scaffold ─────────────────────────────────────────
    def ensure(self) -> "Workspace":
        """Create the project skeleton if missing (idempotent)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
        self.macros_dir.mkdir(parents=True, exist_ok=True)
        for layer in LAYERS:
            (self.models_dir / layer).mkdir(parents=True, exist_ok=True)
        (self.dir / "dbt_project.yml").write_text(_DBT_PROJECT_YML, encoding="utf-8")
        (self.dir / "profiles.yml").write_text(
            _profiles_yml(self.warehouse_path), encoding="utf-8"
        )
        (self.macros_dir / "mmm_generic_tests.sql").write_text(
            _MMM_GENERIC_TESTS, encoding="utf-8"
        )
        return self

    def clean_target(self) -> None:
        """Remove stale run artifacts so we never read a previous invocation's output."""
        rr = self.target_dir / "run_results.json"
        try:
            rr.unlink()
        except FileNotFoundError:
            pass

    # ── raw upload loading ───────────────────────────────
    def load_raw(self, tables: dict[str, pd.DataFrame]) -> list[str]:
        """Materialise raw uploads into the warehouse ``raw`` schema and (re)write
        ``sources.yml``. Returns the loaded (safe) table names.

        The connection is opened, used, and closed here so dbt — the single-writer
        of the DuckDB file — can open it afterwards.
        """
        self.ensure()
        con = duckdb.connect(str(self.warehouse_path))
        loaded: list[str] = []
        try:
            con.execute(f"create schema if not exists {RAW_SCHEMA}")
            used: set[str] = set()
            for raw_name, df in tables.items():
                name = sanitize_ident(raw_name) or "raw_table"
                base, i = name, 2
                while name in used:
                    name = f"{base}_{i}"
                    i += 1
                used.add(name)
                con.register("_incoming", df)
                con.execute(
                    f'create or replace table {RAW_SCHEMA}."{name}" as '
                    f"select * from _incoming"
                )
                con.unregister("_incoming")
                loaded.append(name)
            # Drop stale raw tables from earlier loads so the source list (and the
            # AI's grounding) reflects exactly the asset's current uploads.
            existing = [r[0] for r in con.execute(
                "select table_name from information_schema.tables where table_schema = ?",
                [RAW_SCHEMA]).fetchall()]
            for stale in set(existing) - used:
                con.execute(f'drop table if exists {RAW_SCHEMA}."{stale}"')
        finally:
            con.close()
        self._write_sources_yml(loaded)
        return loaded

    def _write_sources_yml(self, table_names: list[str]) -> None:
        lines = ["version: 2", "sources:", f"  - name: {RAW_SCHEMA}",
                 f"    schema: {RAW_SCHEMA}", "    tables:"]
        for name in table_names:
            lines.append(f"      - name: {name}")
        (self.models_dir / "sources.yml").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    # ── model / seed / schema file IO ────────────────────
    def write_model(self, model: ModelFile) -> Path:
        if model.layer not in LAYERS:
            raise ValueError(f"unknown layer {model.layer!r}")
        path = self.model_path(model.layer, model.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model.sql.strip() + "\n", encoding="utf-8")
        return path

    def read_model(self, layer: str, name: str) -> str | None:
        path = self.model_path(layer, name)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def list_models(self) -> list[ModelFile]:
        out: list[ModelFile] = []
        for layer in LAYERS:
            for path in sorted((self.models_dir / layer).glob("*.sql")):
                out.append(ModelFile(layer=layer, name=path.stem,
                                     sql=path.read_text(encoding="utf-8")))
        return out

    def read_seed(self, name: str) -> str | None:
        path = self.seed_path(name)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_seed(self, name: str, csv_text: str) -> Path:
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
        path = self.seed_path(name)
        path.write_text(csv_text if csv_text.endswith("\n") else csv_text + "\n",
                        encoding="utf-8")
        return path

    def write_schema_yml(self, yaml_text: str) -> Path:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        path = self.models_dir / "schema.yml"
        path.write_text(yaml_text.strip() + "\n", encoding="utf-8")
        return path

    # ── grounding info for codegen ───────────────────────
    def raw_tables_info(self) -> dict[str, list[str]]:
        """{raw_table_name: [columns]} from the pre-loaded ``raw`` schema."""
        if not self.warehouse_path.exists():
            return {}
        con = duckdb.connect(str(self.warehouse_path), read_only=True)
        try:
            rows = con.execute(
                "select table_name, column_name from information_schema.columns "
                "where table_schema = ? order by table_name, ordinal_position",
                [RAW_SCHEMA],
            ).fetchall()
        finally:
            con.close()
        out: dict[str, list[str]] = {}
        for table, col in rows:
            out.setdefault(str(table), []).append(str(col))
        return out

    def list_seeds(self) -> dict[str, list[str]]:
        """{seed_name: [header columns]} for every seed CSV."""
        out: dict[str, list[str]] = {}
        for path in sorted(self.seeds_dir.glob("*.csv")):
            first = path.read_text(encoding="utf-8").splitlines()[:1]
            cols = [c.strip() for c in first[0].split(",")] if first else []
            out[path.stem] = cols
        return out

    def clear_models(self) -> None:
        """Remove all model SQL + schema.yml (keep seeds and sources.yml)."""
        for layer in LAYERS:
            for path in (self.models_dir / layer).glob("*.sql"):
                path.unlink()
        schema = self.models_dir / "schema.yml"
        if schema.exists():
            schema.unlink()

    def clear_seeds(self) -> None:
        """Remove all seed CSVs (the compiled pipeline owns the seed set)."""
        for path in self.seeds_dir.glob("*.csv"):
            path.unlink()

    # ── reading published relations ──────────────────────
    def read_relation(self, name: str, schema: str = MODEL_SCHEMA,
                       limit: int | None = None) -> pd.DataFrame:
        """Read a materialised model/seed out of the warehouse (read-only)."""
        con = duckdb.connect(str(self.warehouse_path), read_only=True)
        try:
            sql = f'select * from {schema}."{sanitize_ident(name)}"'
            if limit is not None:
                sql += f" limit {int(limit)}"
            return con.execute(sql).fetch_df()
        finally:
            con.close()
