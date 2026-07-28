"""End-to-end data-engine slice on the PIPELINE path: register → raw upload →
review (per-table profiles + enum candidates) → typed transform pipeline →
dbt build (quality gates) → publish → indicators → bound into model_df.

Run: PATH="$HOME/.local/bin:$PATH" PYTHONPATH=. .venv/bin/python tests/test_dataeng_e2e.py
"""
from __future__ import annotations

import io

import pandas as pd

from app.agents.dataset_cache import invalidate_project, model_df, uses_project_data
from app.dataeng import assets as asset_svc
from app.dataeng.binding import build_published_long_table
from app.dataeng.dbt import binary, service
from app.dataeng.profile import build_review_report
from app.domain.models import (
    AggSpec, FieldMapEntry, IndustryRef, TransformPipeline, TransformStep,
)
from app.store.files import get_files
from app.store.state import get_store

_LONG_CONSTANTS = [
    ("task_name", "'sales.xlsx'"), ("brand", "''"), ("source", "'upload'"),
    ("l1", "'MARKETING FACTOR'"), ("l2", "''"), ("l3", "''"), ("l4", "'Sales'"),
    ("l5", "''"), ("l6", "''"), ("l7", "''"), ("l8", "''"),
    ("metric_type", "'Y'"), ("metric", "'本品销量'"),
]

_GROUP = ["task_name", "brand", "province_group", "channel_type", "channel",
          "year", "month", "source", "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
          "metric_type", "metric"]


def _raw_xlsx() -> bytes:
    months = pd.period_range("2022-01", "2023-12", freq="M").astype(str)
    df = pd.DataFrame({
        "Month": list(months) * 2,
        "Region": ["华东"] * len(months) + ["华南"] * len(months),
        "Channel": ["MT"] * len(months) + ["EC"] * len(months),
        "Sales": [5000 + (i * 137) % 900 for i in range(len(months) * 2)],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def _pipeline() -> TransformPipeline:
    field_map = [
        FieldMapEntry(source="Region", target="province_group"),
        FieldMapEntry(source="Channel", target="channel_type"),
        FieldMapEntry(source="Channel", target="channel"),
        FieldMapEntry(source="Month", target="ym"),
        FieldMapEntry(source="Sales", target="value", cast="double"),
    ] + [FieldMapEntry(target=t, expr=e) for t, e in _LONG_CONSTANTS]
    return TransformPipeline(steps=[
        TransformStep(id="fm", kind="field_map", name="map sales",
                      note="Rename raw columns onto the long-table shape.",
                      inputs=["source:raw"], fieldMap=field_map),
        TransformStep(id="dv", kind="derive", name="time columns", inputs=["fm"],
                      derive=[
                          {"name": "year", "expr": "cast(substr(replace(ym,'-',''),1,4) as integer)"},
                          {"name": "month", "expr": "cast(replace(ym,'-','') as integer)"},
                      ]),
        TransformStep(id="agg", kind="aggregate", name="mart", inputs=["dv"],
                      groupBy=_GROUP, aggs=[AggSpec(column="value", func="sum")]),
    ], outputStep="agg")


def main() -> int:
    ok, msg = binary.available()
    print(f"[binary] {msg}")
    if not ok:
        print("SKIP: dbt binary unavailable")
        return 0

    store = get_store()
    files = get_files()
    meta = store.create("DataEng E2E", "TestBrand",
                        IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"))
    pid = meta.id
    try:
        st = store.get(pid)
        assert st is not None

        # 1) register asset + raw upload
        rec = files.add(pid, "raw_data", "sales.xlsx", _raw_xlsx())
        assert rec.parsed, rec.parse_error
        asset = asset_svc.create_asset(st, "Sales E2E", source_file_ids=[rec.id])

        # 2) per-table review, with full enum candidates for categorical fields
        asset.review = build_review_report(pid, asset)
        asset.raw_tables = asset.review.tables
        assert asset.review.time_field == "Month", asset.review.time_field
        enum_fields = {f.name: f.enum_values for f in asset.review.fields if f.enum_values}
        assert set(enum_fields.get("Channel", [])) == {"MT", "EC"}, enum_fields
        print(f"✓ review: {asset.review.column_count} fields, enum candidates: {list(enum_fields)}")

        # 3) typed pipeline → deterministic compile → dbt build (quality gates)
        asset.pipeline = _pipeline()
        summary = service.build(st, pid, asset)
        assert summary.ok, f"build failed: {summary.error}"
        assert summary.step_models, "step→model mapping missing"
        assert summary.tests > 0 and summary.failed == 0
        print(f"✓ build: {summary.models} models, {summary.passed}/{summary.tests} tests passed")

        # 4) publish → parquet + indicators (factor-path grounded)
        ver = service.publish(pid, st, asset)
        assert ver.version == 1 and asset.status == "published"
        assert st.indicators and st.indicators[0].metric == "本品销量"
        print(f"✓ published v{ver.version}: {ver.row_count} rows; {len(st.indicators)} indicator(s)")

        # 5) binding + model_df serve the published asset (not the reference)
        bound = build_published_long_table(pid, st)
        assert bound is not None and not bound.empty
        invalidate_project(pid)
        df = model_df(st)
        assert uses_project_data(st), "model_df should serve project data"
        assert df["metric_type"].isin(["Y"]).all()
        assert df["month"].dropna().nunique() == 24
        print(f"✓ model_df serves project data: {len(df)} rows, "
              f"{df['month'].dropna().nunique()} months")

        print("\nALL DATAENG E2E TESTS PASSED")
        return 0
    finally:
        invalidate_project(pid)
        store.delete(pid)
        files.purge(pid)


if __name__ == "__main__":
    raise SystemExit(main())
