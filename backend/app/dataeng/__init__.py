"""Data Engine — project-scoped raw-data cleaning + reusable data assets.

Client data rarely arrives in our standard collection format, so the data engine
turns arbitrary raw uploads into a registered **data asset** = a slice of the
2.21 unified long table. The flow:

    register source → per-table review (4 qualities + enum candidates) → typed
    transform pipeline (AI-drafted, human-reviewed steps) → dbt build with data-
    quality gates → publish (parquet + indicators) → fed to model_df

Modules:
    duck.py     DuckDB sandbox kernel (sanitize_ident + locked-down preview runner)
    profile.py  review profiling engine (granularity / continuity / volatility / enums)
    assets.py   asset registry + parquet version persistence
    binding.py  published asset → 2.21 long table (replaces slot binding)
    dbt/        the transform engine: pipeline model → compiler → dbt executor
"""
