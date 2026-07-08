"""Data Engine — project-scoped raw-data cleaning + reusable data assets.

Client data rarely arrives in our standard collection format, so the data engine
turns arbitrary raw uploads into a registered **data asset** = a slice of the
2.21 unified long table. The flow:

    register source → quick review (profiling + charts) → field-level cleaning
    spec → AI-drafted DuckDB SQL → preview → publish (parquet) → fed to model_df

Modules:
    duck.py     DuckDB sandbox execution kernel (locked-down SQL runner)
    profile.py  quick-review profiling engine (granularity / continuity / volatility)
    sql_gen.py  LLM-driven DuckDB SQL drafting from a cleaning spec
    assets.py   DataAssetStore: registry + parquet persistence + versioning
    binding.py  published asset → 2.21 long table (replaces slot binding)
"""
