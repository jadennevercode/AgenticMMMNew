"""Aggregate ``summarize()`` over all reference loaders for sanity reporting."""
from __future__ import annotations

from typing import Any

from .business import load_industry_knowledge, load_kbqs, load_scope
from .data_dictionary import load_data_dictionary
from .dataset import load_model_dataset
from .factor_tree import load_factor_tree
from .interviews import load_interviews
from .validation import load_validation_rules


def _safe(fn) -> tuple[Any, str | None]:
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001 - summary must not crash
        return None, f"{type(exc).__name__}: {exc}"


def summarize() -> dict:
    """Quick counts of every reference source, with per-loader error capture."""
    summary: dict = {}
    errors: dict[str, str] = {}

    df, err = _safe(load_model_dataset)
    if err:
        errors["model_dataset"] = err
    else:
        summary["model_dataset"] = {
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "columns": list(df.columns),
            "brands": sorted(df["brand"].dropna().unique().tolist()),
            "channel_types": sorted(df["channel_type"].dropna().unique().tolist()),
            "channels": sorted(df["channel"].dropna().unique().tolist()),
            "l1": sorted(df["l1"].dropna().unique().tolist()),
            "l2": sorted(df["l2"].dropna().unique().tolist()),
            "years": sorted(int(y) for y in df["year"].dropna().unique().tolist()),
            "value_non_null": int(df["value"].notna().sum()),
        }

    tree, err = _safe(load_factor_tree)
    if err:
        errors["factor_tree"] = err
    else:
        summary["factor_tree"] = {
            "counts": tree["counts"],
            "l1_values": tree["l1_values"],
            "l2_values": tree["l2_values"],
        }

    rules, err = _safe(load_validation_rules)
    if err:
        errors["validation_rules"] = err
    else:
        summary["validation_rules"] = {
            "dimensions": {
                k: len(v["criteria"]) for k, v in rules["dimensions"].items()
            },
            "principle_lines": len(rules["principles"]),
        }

    dd, err = _safe(load_data_dictionary)
    if err:
        errors["data_dictionary"] = err
    else:
        y_x = {}
        for r in dd:
            y_x[r.get("y_or_x", "") or "(blank)"] = y_x.get(
                r.get("y_or_x", "") or "(blank)", 0) + 1
        summary["data_dictionary"] = {"rows": len(dd), "y_or_x_breakdown": y_x}

    scope, err = _safe(load_scope)
    if err:
        errors["scope"] = err
    else:
        summary["scope"] = {"entries": len(scope["entries"]), "notes": len(scope["notes"])}

    kbqs, err = _safe(load_kbqs)
    if err:
        errors["kbqs"] = err
    else:
        summary["kbqs"] = {"count": len(kbqs)}

    ind, err = _safe(load_industry_knowledge)
    if err:
        errors["industry_knowledge"] = err
    else:
        summary["industry_knowledge"] = {
            "sheets": ind["sheets"],
            "rows_per_sheet": {k: len(v) for k, v in ind["sections"].items()},
        }

    interviews, err = _safe(load_interviews)
    if err:
        errors["interviews"] = err
    else:
        summary["interviews"] = {
            "count": len(interviews),
            "layers": sorted({i["layer"] for i in interviews if i["layer"]}),
            "roles": sorted({i["role"] for i in interviews if i["role"]}),
            "total_chars": sum(len(i["text"]) for i in interviews),
            "parse_errors": [i["filename"] for i in interviews if i.get("error")],
        }

    if errors:
        summary["errors"] = errors
    return summary
