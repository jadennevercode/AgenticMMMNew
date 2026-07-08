"""Smoke test: call every loader against the REAL reference files and print shapes.

Run from the backend dir:
    .venv/bin/python -m app.ingest._smoke
"""
from __future__ import annotations

import json

from app.ingest import (
    load_data_dictionary,
    load_factor_tree,
    load_industry_knowledge,
    load_interviews,
    load_kbqs,
    load_model_dataset,
    load_scope,
    load_validation_rules,
    summarize,
)


def main() -> None:
    print("== load_model_dataset ==")
    df = load_model_dataset()
    print("  shape:", df.shape)
    print("  columns:", list(df.columns))
    print("  channel_type:", sorted(df["channel_type"].dropna().unique().tolist()))
    print("  channel:", sorted(df["channel"].dropna().unique().tolist()))
    print("  L1:", sorted(df["l1"].dropna().unique().tolist()))
    print("  L2:", sorted(df["l2"].dropna().unique().tolist()))
    print("  value dtype:", df["value"].dtype, "non-null:", int(df["value"].notna().sum()))

    print("\n== load_factor_tree ==")
    tree = load_factor_tree()
    print("  counts:", tree["counts"])
    print("  L1 values:", tree["l1_values"])
    print("  L2 values:", tree["l2_values"])

    print("\n== load_validation_rules ==")
    rules = load_validation_rules()
    print("  dimensions:", {k: len(v["criteria"]) for k, v in rules["dimensions"].items()})
    print("  principle lines:", len(rules["principles"]))

    print("\n== load_data_dictionary ==")
    dd = load_data_dictionary()
    print("  rows:", len(dd))
    print("  sample keys:", list(dd[0].keys()) if dd else [])

    print("\n== load_scope ==")
    scope = load_scope()
    print("  entries:", len(scope["entries"]), "notes:", len(scope["notes"]))

    print("\n== load_kbqs ==")
    kbqs = load_kbqs()
    print("  count:", len(kbqs))
    if kbqs:
        print("  first:", kbqs[0]["code"], kbqs[0]["question"][:50])

    print("\n== load_industry_knowledge ==")
    ind = load_industry_knowledge()
    print("  sheets:", ind["sheets"])

    print("\n== load_interviews ==")
    interviews = load_interviews()
    print("  count:", len(interviews))
    for i in interviews:
        flag = " ERROR" if i.get("error") else ""
        print(f"    {i['layer']:7} {i['role']:11} chars={len(i['text']):6}{flag}  {i['filename'][:40]}")

    print("\n== summarize ==")
    print(json.dumps(summarize(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
