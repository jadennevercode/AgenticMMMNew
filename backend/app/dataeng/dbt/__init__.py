"""dbt Fusion transform engine for the Data Engine.

Each project owns a real **dbt project** on disk under ``data/projects/{id}/dbt/``.
Client uploads are messy and multi-source; dbt gives analysts the full power of
SQL + a dependency DAG + data tests to normalise them into the 2.21 target long
table, and the output is a portable, inspectable dbt project (not a bespoke DSL).

Layering (dbt-idiomatic):

    seeds/                  master-data / enum dictionaries (small, human-edited CSV)
    models/sources.yml      raw uploads, pre-loaded by us into the ``raw`` schema
    models/staging/         one stg_* per raw table: rename / cast / unpivot
    models/intermediate/    int_*: union, enum-join (seed), aggregate
    models/marts/           asset_*: final rows matching the target schema
    models/schema.yml       data tests (not_null / unique / accepted_values / custom)

Disk is the source of truth for the dbt files (like the parquet outputs, they are
too detailed for state JSON); ``ProjectState`` keeps only the last run summary for
the UI. Execution is the real ``dbt`` binary via subprocess — see:

    binary.py     locate + version-check the pinned dbt Fusion binary
    workspace.py  scaffold the project, pre-load raw tables, read/write model files
    executor.py   run dbt commands and parse target/*.json artifacts (the ONLY
                  module that touches dbt artifact formats — isolates alpha churn)
"""
