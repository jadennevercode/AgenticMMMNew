"""Security + correctness smoke test for the DuckDB sandbox kernel.

Run: .venv/bin/python -m app.dataeng._test_duck
"""
from __future__ import annotations

import pandas as pd

from app.dataeng.duck import SqlSafetyError, run_clean_sql, validate_sql


def _expect_blocked(sql: str) -> None:
    try:
        validate_sql(sql)
    except SqlSafetyError:
        return
    raise AssertionError(f"expected blocked but allowed: {sql!r}")


def _expect_allowed(sql: str) -> None:
    validate_sql(sql)  # raises if blocked


def main() -> None:
    # ── allowlist ────────────────────────────────────────
    _expect_allowed("SELECT * FROM raw")
    _expect_allowed("WITH x AS (SELECT 1) SELECT * FROM x")
    _expect_allowed("select a, created_at from raw where a > 0")  # 'create' substring is fine

    # ── banned: DDL/DML ──────────────────────────────────
    _expect_blocked("DROP TABLE raw")
    _expect_blocked("INSERT INTO raw VALUES (1)")
    _expect_blocked("UPDATE raw SET a=1")
    _expect_blocked("DELETE FROM raw")
    _expect_blocked("CREATE TABLE x AS SELECT 1")
    _expect_blocked("ALTER TABLE raw ADD COLUMN b int")

    # ── banned: config + file/network access ─────────────
    _expect_blocked("SET enable_external_access=true")
    _expect_blocked("PRAGMA database_list")
    _expect_blocked("ATTACH 'x.db'")
    _expect_blocked("COPY raw TO 'out.csv'")
    _expect_blocked("SELECT * FROM read_csv('/etc/passwd')")
    _expect_blocked("SELECT * FROM read_parquet('s3://bucket/x.parquet')")
    _expect_blocked("INSTALL httpfs")

    # ── banned: multiple statements ──────────────────────
    _expect_blocked("SELECT 1; DROP TABLE raw")
    print("✓ allowlist / banned-token checks pass")

    # ── execution: real cleaning ─────────────────────────
    raw = pd.DataFrame({
        "Month": ["2023-01", "2023-02", "2023-03"],
        "Spend": ["100", "200", "-5"],
        "Region": ["华东", "华东", "华南"],
    })
    res = run_clean_sql(
        "SELECT Region AS province_group, CAST(Spend AS DOUBLE) AS value FROM raw "
        "WHERE CAST(Spend AS DOUBLE) >= 0",
        {"raw": raw},
    )
    assert res.ok, res.error
    assert res.row_count == 2, res.row_count
    assert res.columns == ["province_group", "value"], res.columns
    assert res.df is not None and len(res.df) == 2
    print(f"✓ clean query produced {res.row_count} rows, cols={res.columns}")

    # ── execution: file access is blocked at runtime too ─
    blocked = run_clean_sql("SELECT * FROM read_csv('/etc/passwd')", {"raw": raw})
    assert not blocked.ok, "read_csv should be blocked"
    print("✓ runtime file access blocked")

    # ── execution: bad SQL surfaces as error, not crash ──
    bad = run_clean_sql("SELECT nope FROM raw", {"raw": raw})
    assert not bad.ok and "SQL error" in bad.error, bad
    print("✓ invalid column surfaces as error")

    print("\nALL DUCK KERNEL TESTS PASSED")


if __name__ == "__main__":
    main()
