"""Verify the 4 MMM data-quality generic tests fire correctly.

Run:  PYTHONPATH=. .venv/bin/python -m app.dataeng.dbt._test_generic_tests

Each scenario model carries exactly the test it should trigger; a 'good' model
carries all four and must pass every one. We build once and assert per-test status.
"""
from __future__ import annotations

import shutil
import sys

from app.dataeng.dbt import binary, executor
from app.dataeng.dbt.workspace import ModelFile, Workspace

PROJECT_ID = "_dbt_gtest"

# monthly DATE series generator; `value` varies with n
_MONTHLY = ("{{{{ config(materialized='table') }}}}\n"
            "select (date '{start}' + interval '1 month' * n) as period_date, "
            "(n * 1.3) as value\nfrom generate_series(0, {last}) as t(n)")


def _models(ws: Workspace) -> None:
    # good: 2022-01..2024-12 monthly (36 pts, >2y, monthly, varies, 12/12/12)
    ws.write_model(ModelFile("marts", "good_series",
                             _MONTHLY.format(start="2022-01-01", last=35)))
    # short: only 2023 (12 pts) → time span < 2y
    ws.write_model(ModelFile("marts", "short_series",
                             _MONTHLY.format(start="2023-01-01", last=11)))
    # flat: 24 monthly pts but constant value → no variation
    ws.write_model(ModelFile("marts", "flat_series",
        "{{ config(materialized='table') }}\n"
        "select (date '2022-01-01' + interval '1 month' * n) as period_date, "
        "5.0 as value\nfrom generate_series(0, 23) as t(n)"))
    # yearly: 5 yearly pts → granularity coarser than monthly
    ws.write_model(ModelFile("marts", "yearly_series",
        "{{ config(materialized='table') }}\n"
        "select (date '2019-01-01' + interval '1 year' * n) as period_date, "
        "(n * 2.0) as value\nfrom generate_series(0, 4) as t(n)"))
    # partial: 2022:12, 2023:12, 2024:3 → years not comparable
    ws.write_model(ModelFile("marts", "partial_series",
        "{{ config(materialized='table') }}\n"
        "select (date '2022-01-01' + interval '1 month' * n) as period_date, "
        "(n * 1.1) as value\nfrom generate_series(0, 26) as t(n)"))

    ws.write_schema_yml("""\
version: 2
models:
  - name: good_series
    columns:
      - name: period_date
        tests:
          - time_span_min_years:
              arguments: {min_years: 2}
          - time_granularity_allowed
          - yoy_comparable
      - name: value
        tests:
          - has_variation
  - name: short_series
    columns:
      - name: period_date
        tests:
          - time_span_min_years:
              arguments: {min_years: 2}
  - name: flat_series
    columns:
      - name: value
        tests:
          - has_variation
  - name: yearly_series
    columns:
      - name: period_date
        tests:
          - time_granularity_allowed
  - name: partial_series
    columns:
      - name: period_date
        tests:
          - yoy_comparable
""")


def main() -> int:
    ok, msg = binary.available()
    print(f"[binary] {msg}")
    if not ok:
        print("SKIP: dbt binary unavailable")
        return 0

    ws = Workspace(PROJECT_ID)
    shutil.rmtree(ws.dir, ignore_errors=True)
    ws.ensure()
    _models(ws)

    res = executor.build(ws)
    status = {t.name: t.status for t in res.tests}
    for name, st in sorted(status.items()):
        print(f"    {st:6} {name}")

    def find(prefix: str) -> str:
        hits = [s for n, s in status.items() if n.startswith(prefix)]
        assert hits, f"no test node matching {prefix!r} in {list(status)}"
        return hits[0]

    # good_series: all four pass
    assert find("time_span_min_years_good_series") == "pass"
    assert find("time_granularity_allowed_good_series") == "pass"
    assert find("yoy_comparable_good_series") == "pass"
    assert find("has_variation_good_series") == "pass"
    # each bad scenario: its attached test fails
    assert find("time_span_min_years_short_series") == "fail", "short span should fail"
    assert find("has_variation_flat_series") == "fail", "flat value should fail"
    assert find("time_granularity_allowed_yearly_series") == "fail", "yearly should fail"
    assert find("yoy_comparable_partial_series") == "fail", "partial years should fail"

    print("PASS — all 4 generic tests fire correctly (good passes, bad fails)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
