"""2.3a anomaly review — the handling must actually reach the model.

The set this replaces (`ai-2.3`) asked how anomalies should be handled, stored
the answer, and never read it. These tests exist so that cannot happen again:
each one asserts a *ruling* changes the fit, and that an unruled card does not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.ledger import anomaly_effects, model_selection
from app.domain.models import (
    AnomalyHypothesis,
    AnomalyReview,
    OlsCapWindow,
    OlsConfig,
    OlsParams,
)
from app.mmm.engine import _build_controls
from app.mmm.pivot import _winsorize_windows
from app.store.state import danone_meta, initial_state


def _card(handling: str, status: str = "accepted") -> AnomalyHypothesis:
    return AnomalyHypothesis(
        id="an-0", channel="EC", year="2024", growthPct=62.0,
        hypothesis="Platform subsidy war.", proposed="event",
        status=status, handling=handling, start=202401, end=202412,
    )


def _state_with(card: AnomalyHypothesis):
    st = initial_state(danone_meta())
    st.anomaly_review = AnomalyReview(rows=[card])
    st.ols_config = OlsConfig(params=OlsParams())
    return st


def test_accepted_event_becomes_a_dummy_control() -> None:
    events, caps = anomaly_effects(_state_with(_card("event")))
    assert len(events) == 1 and not caps
    assert events[0].start == 202401 and events[0].end == 202412
    assert "EC" in events[0].label and "2024" in events[0].label


def test_accepted_cap_becomes_a_cap_window() -> None:
    events, caps = anomaly_effects(_state_with(_card("cap")))
    assert not events and len(caps) == 1
    assert caps[0].start == 202401 and caps[0].end == 202412


def test_raw_has_no_numeric_effect() -> None:
    events, caps = anomaly_effects(_state_with(_card("raw")))
    assert not events and not caps


def test_a_pending_or_rejected_card_never_touches_the_model() -> None:
    """An unreviewed hypothesis must not quietly reshape the fit."""
    for status in ("pending", "rejected"):
        events, caps = anomaly_effects(_state_with(_card("event", status=status)))
        assert not events and not caps, status


def test_effects_reach_the_resolved_selection() -> None:
    """model_selection is what 2.5r / 2.6 / 3.2 fit on — the events must be there."""
    sel = model_selection(_state_with(_card("event")))
    assert sel.params is not None
    assert len(sel.params.events) == 1
    assert sel.params.events[0].start == 202401


def test_event_dummy_marks_exactly_its_window() -> None:
    """The dummy is 1 inside the window and 0 outside — nothing else."""
    idx = pd.Index([202311, 202312, 202401, 202406, 202412, 202501], name="month")
    mf = type("MF", (), {"frame": pd.DataFrame({"Y": range(len(idx))}, index=idx)})()
    events, _ = anomaly_effects(_state_with(_card("event")))
    ctrl = _build_controls(mf, OlsParams(trend="none", seasonality="none", events=events))

    col = next(c for c in ctrl.columns if c.startswith("_ev"))
    assert list(ctrl[col]) == [0.0, 0.0, 1.0, 1.0, 1.0, 0.0]


def test_event_window_covering_everything_is_dropped() -> None:
    """A constant control has no variance and would break the normal equations."""
    idx = pd.Index([202401, 202402, 202403], name="month")
    mf = type("MF", (), {"frame": pd.DataFrame({"Y": [1, 2, 3]}, index=idx)})()
    events, _ = anomaly_effects(_state_with(_card("event")))
    ctrl = _build_controls(mf, OlsParams(trend="none", seasonality="none", events=events))
    assert not [c for c in ctrl.columns if c.startswith("_ev")]


def test_capping_clips_only_inside_the_window() -> None:
    y = pd.Series([10.0, 10.0, 10.0, 10.0, 900.0, 10.0, 10.0, 10.0, 10.0, 10.0],
                  index=[202301, 202302, 202303, 202304, 202405,
                         202406, 202407, 202408, 202409, 202410])
    caps = [OlsCapWindow(start=202405, end=202405)]
    out = _winsorize_windows(y, caps)

    assert out.loc[202405] < 900.0, "the spike inside the window must be clipped"
    assert out.loc[202405] == float(y.quantile(0.95))
    untouched = [k for k in y.index if k != 202405]
    assert all(out.loc[k] == y.loc[k] for k in untouched), "outside the window nothing moves"


def test_capping_without_windows_is_the_identity() -> None:
    y = pd.Series([1.0, 2.0, 900.0], index=[202401, 202402, 202403])
    assert _winsorize_windows(y, []).equals(y)
    assert np.isclose(_winsorize_windows(y, []).loc[202403], 900.0)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all anomaly-review tests passed")
