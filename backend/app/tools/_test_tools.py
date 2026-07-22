"""Tool wrappers are identity wrappers — registering a check changed no number.

Run: PYTHONPATH=. .venv/bin/python -m app.tools._test_tools

The load-bearing claim: routing a computation through the registry produces the
byte-identical result of calling the implementation directly, and the 2.2
scorecard composed from the four quality tools equals `score_quality`. If this
ever fails, the tool layer has started doing arithmetic and must be reverted —
it exists to make calls visible, not to change them.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from app.agents import quality_scoring
from app.agents.data_rules import reference_cv, vif_all
from app.agents.quality_scoring import FieldContext, roll_up_quality, score_quality
from app.agents.stat_scoring import pearson
from app.tools import TOOLS, get, list_specs
from app.tools.tracing import tool_run

PROJECT_ID = "danone-mizone"


def _state():
    from app.store.state import get_store

    st = get_store().get(PROJECT_ID)
    if st is None:
        print(f"skip: project {PROJECT_ID} not present")
        return None
    return st


def _series_evidence(df: pd.DataFrame, limit: int = 40):
    """Real evidence + field context for the first `limit` metric series."""
    from app.agents.data import _field_context

    fields = _field_context(df)
    evidences, contexts = [], []
    for (l1, l2, l3, l4, metric), grp in df.groupby(["l1", "l2", "l3", "l4", "metric"], dropna=False):
        if not str(metric).strip() or str(metric) == "<NA>":
            continue
        evidences.append(quality_scoring.compute_series_evidence(grp))
        contexts.append(fields.get((l1, l2, l3, l4), FieldContext(False, True)))
        if len(evidences) >= limit:
            break
    return evidences, contexts


def test_registry_shape() -> None:
    specs = list_specs()
    assert len(specs) == 8, len(specs)
    assert {s.category for s in specs} == {"quality", "statistical", "model"}
    for s in specs:
        assert s.id in TOOLS and s.description and s.input_summary and s.output_summary
    print(f"  registry: {len(specs)} tools")


def test_quality_tools_identity(df: pd.DataFrame) -> None:
    evidences, contexts = _series_evidence(df)
    assert evidences, "no series to score"
    by_dim = [
        get("quality.consistency").run(evidences),
        get("quality.accuracy").run(evidences),
        get("quality.completeness").run(evidences, contexts),
        get("quality.granularity").run(evidences),
    ]
    for i, (ev, fld) in enumerate(zip(evidences, contexts)):
        assert by_dim[0][i] == quality_scoring._consistency_subs(ev)
        assert by_dim[1][i] == quality_scoring._accuracy_subs(ev)
        assert by_dim[2][i] == quality_scoring._completeness_subs(ev, fld)
        assert by_dim[3][i] == quality_scoring._granularity_subs(ev)
        # …and the tool-composed scorecard row equals the direct one, cell for cell.
        composed = roll_up_quality([s for dim in by_dim for s in dim[i]])
        assert composed == score_quality(ev, fld), (composed, score_quality(ev, fld))
    print(f"  quality: {len(evidences)} series identical across 4 tools + rollup")


def test_stat_tools_identity(df: pd.DataFrame) -> None:
    from app.agents.stat_scoring import _indicator_series, _monthly_y

    metas, wide = _indicator_series(df)
    y = _monthly_y(df)
    assert metas and y is not None, "no indicators / no KPI"
    cols = [m["col"] for m in metas][:60]
    matrix = wide[cols].to_numpy(dtype=float)
    y_aligned = y.reindex(wide.index)

    assert np.array_equal(get("stat.vif").run([matrix]), vif_all(matrix), equal_nan=True)
    m2 = matrix[:, :2]
    assert np.array_equal(get("stat.vif").run([matrix, m2]),
                          list(vif_all(matrix)) + list(vif_all(m2)), equal_nan=True)
    assert get("stat.cv").run([wide[c].to_numpy(dtype=float) for c in cols]) == \
        [reference_cv(wide[c].to_numpy(dtype=float)) for c in cols]
    assert get("stat.pearson").run([wide[c] for c in cols], y_aligned) == \
        [pearson(wide[c], y_aligned) for c in cols]
    print(f"  statistical: {len(cols)} indicators identical across CV / Pearson / VIF")


def test_ols_tool_identity(st, df: pd.DataFrame) -> None:
    from app.agents.dataset_cache import model_objects
    from app.mmm import run_mmm

    objs = list(model_objects(st))[:1]
    if not objs:
        print("  ols: no model objects — skipped")
        return
    obj = objs[0]
    direct = run_mmm(df, obj, adstock=0.5, hill_half=1.0)
    viatool = get("model.ols").run(df, obj, adstock=0.5, hill_half=1.0)
    assert direct.r2 == viatool.r2 and direct.n_obs == viatool.n_obs
    assert direct.drivers == viatool.drivers
    assert direct.contribution == viatool.contribution
    assert direct.coefficients == viatool.coefficients
    print(f"  model: OLS on '{obj}' identical (R²={direct.r2:.4f})")


def test_tracing_records(st) -> None:
    """A traced call records one invocation with a real duration; errors record too."""
    before = len(st.tool_invocations)
    with tool_run(None, st, "2.4", "stat.cv", "2 series") as h:
        h.result("ok")
    rec = st.tool_invocations[0]
    assert len(st.tool_invocations) == before + 1
    assert rec.status == "ok" and rec.tool_id == "stat.cv" and rec.task_id == "2.4"
    assert rec.duration_ms is not None and rec.result_summary == "ok"

    try:
        with tool_run(None, st, "2.4", "stat.vif", "boom"):
            raise ValueError("boom")
    except ValueError:
        pass
    assert st.tool_invocations[0].status == "error"
    assert "boom" in st.tool_invocations[0].error
    # leave the state as we found it — this is the live project's blackboard
    del st.tool_invocations[:2]
    print("  tracing: ok + error invocations recorded with durations")


def main() -> int:
    print("tool registry")
    test_registry_shape()
    st = _state()
    if st is None:
        return 0
    from app.agents.dataset_cache import model_df

    df = model_df(st)
    test_tracing_records(st)
    test_quality_tools_identity(df)
    test_stat_tools_identity(df)
    test_ols_tool_identity(st, df)
    print("all tool tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
