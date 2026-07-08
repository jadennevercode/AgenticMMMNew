"""End-to-end data-engine slice: register → profile → SQL preview → publish →
bound into model_df. Uses a hand-written cleaning SQL (no LLM).

Run: PYTHONPATH=. .venv/bin/python tests/test_dataeng_e2e.py
"""
from __future__ import annotations

import io

import pandas as pd

from app.agents.dataset_cache import invalidate_project, model_df, uses_project_data
from app.dataeng import assets as asset_svc
from app.dataeng.binding import build_published_long_table
from app.dataeng.profile import build_review_report
from app.dataeng.sql_gen import run_preview
from app.domain.models import CleaningSpec, FieldRule
from app.store.files import get_files
from app.store.state import get_store
from app.domain.models import IndustryRef

# A hand-written cleaning SQL that long-table-izes the raw sheet onto the 2.21 schema.
_CLEAN_SQL = """
SELECT 'sales.xlsx' AS task_name, '' AS brand, Region AS province_group,
  Channel AS channel_type, Channel AS channel,
  CAST(substr(replace(Month,'-',''),1,4) AS INTEGER) AS year,
  CAST(replace(Month,'-','') AS INTEGER) AS month,
  'upload' AS source, 'MARKETING FACTOR' AS l1, '' AS l2, '' AS l3, 'Sales' AS l4,
  '' AS l5, '' AS l6, '' AS l7, '' AS l8,
  'Y' AS metric_type, '本品销量' AS metric, CAST(Sales AS DOUBLE) AS value
FROM raw
UNION ALL
SELECT 'sales.xlsx', '', Region, Channel, Channel,
  CAST(substr(replace(Month,'-',''),1,4) AS INTEGER), CAST(replace(Month,'-','') AS INTEGER),
  'upload', 'MARKETING FACTOR', '', '', 'Spend', '', '', '', '',
  'spending', '花费', CAST(Spend AS DOUBLE)
FROM raw
"""


def _raw_xlsx() -> bytes:
    months = [f"2023-{m:02d}" for m in range(1, 13)]
    rows = []
    for region in ("华东", "华南"):
        for i, mo in enumerate(months):
            rows.append({"Month": mo, "Region": region, "Channel": "MT",
                         "Spend": 1000 + i * 30, "Sales": 5000 + i * 120})
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def main() -> None:
    store = get_store()
    meta = store.create("DataEng E2E", "TestBrand",
                        IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"))
    pid = meta.id
    try:
        st = store.get(pid)
        assert st is not None

        # 1) register raw source file
        rec = get_files().add(pid, "raw_data", "sales.xlsx", _raw_xlsx())
        assert rec.parsed, rec.parse_error
        print(f"✓ raw uploaded: {rec.filename} ({rec.parse_chars} chars)")

        # 2) create asset + profile
        asset = asset_svc.create_asset(st, "Mizone sell-out", source_file_ids=[rec.id])
        asset.review = build_review_report(pid, asset)
        asset.raw_tables = asset.review.tables
        asset.status = "reviewed"
        assert asset.review.time_field == "Month", asset.review.time_field
        assert asset.review.row_count == 24, asset.review.row_count
        print(f"✓ review: time={asset.review.time_field}/{asset.review.time_granularity}, "
              f"{asset.review.column_count} fields, charts={[c['id'] for c in asset.review.charts]}")

        # 3) cleaning spec (illustrative) + SQL preview via sandbox
        asset.cleaning_spec = CleaningSpec(rules=[
            FieldRule(id="r1", sourceField="Month", targetColumn="month",
                      transform="transform", rule="'2023-01' → 202301"),
            FieldRule(id="r2", sourceField="Sales", targetColumn="value",
                      transform="passthrough"),
        ], targetSchema=[])
        draft = run_preview(pid, asset, _CLEAN_SQL)
        assert draft.status == "ok", draft.error
        assert draft.row_count == 48, draft.row_count
        assert "metric_type" in draft.preview_columns
        asset.sql_draft = draft
        asset.status = "cleaned"
        print(f"✓ SQL preview ok: {draft.row_count} long rows, cols={len(draft.preview_columns)}")

        # 4) publish → parquet version
        ver = asset_svc.publish_asset(pid, st, asset)
        assert ver.version == 1 and ver.row_count == 48, ver
        assert asset.status == "published"
        print(f"✓ published v{ver.version}: {ver.row_count} rows → {ver.parquet_path}")

        # 5) binding + model_df now serves the published asset (not reference)
        bound = build_published_long_table(pid, st)
        assert bound is not None and len(bound) == 48, None if bound is None else len(bound)
        invalidate_project(pid)
        df = model_df(st)
        assert uses_project_data(st), "model_df should serve project data"
        assert df["metric_type"].isin(["Y", "spending"]).all()
        assert df["month"].dropna().nunique() == 12
        print(f"✓ model_df serves project data: {len(df)} rows, "
              f"{df['month'].dropna().nunique()} months, objects={sorted(df['channel_type'].unique())}")

        print("\nALL DATAENG E2E TESTS PASSED")
    finally:
        invalidate_project(pid)
        store.delete(pid)
        get_files().purge(pid)


if __name__ == "__main__":
    main()
