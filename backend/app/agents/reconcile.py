"""Why the factor count changes between 2.1, 2.2 and 2.4.

The three S2 screening artifacts count three different populations, and until this
existed none of them said so — 2.1 shows 177 factor-tree rows of which 16 are
mapped, 2.2 scores 85 metric groups, 2.4 scores 29. A reader comparing the headline
numbers concludes data is being lost. Some of it is, and the reasons are all
legitimate; the problem was that they were invisible.

The populations, in order:

* **2.1 Data Processing** — the *declared* target: every active factor-tree row.
  Its "mapped" count is how many of those a published asset actually covers.
* **2.2 Data Quality** — the *supplied* population: one row per
  ``(l1..l4, metric)`` group present in the assembled table. This is not a subset
  of 2.1: a published metric that no factor row claims is still scored, and a
  factor row nothing supplies is not. The two key spaces differ — the factor map
  keys on the row's declared ``indicator``, the data keys on its ``metric``.
* **2.4 Statistical Score** — 2.2's population minus the response itself (a KPI is
  not a candidate driver), minus anything an earlier layer already rejected, minus
  anything constant across the whole panel.

This module derives the chain and renders it as a sheet both artifacts carry, so
each delta is attributable rather than inferred.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RECONCILE_COLUMNS = ["Stage", "Count", "What it counts", "Change from the line above"]


@dataclass(frozen=True)
class Reconciliation:
    tree_rows: int = 0
    tree_mapped: int = 0
    tree_ignored: int = 0
    supplied_groups: int = 0
    supplied_unclaimed: int = 0
    scored_quality: int = 0
    quality_inherited: int = 0
    scored_statistical: int = 0
    stat_response: int = 0
    stat_inherited: int = 0
    stat_no_variance: int = 0
    notes: list[str] = field(default_factory=list)

    def rows(self) -> list[list[str]]:
        """The chain as artifact rows — every step carries its own delta."""
        out: list[list[str]] = [
            ["2.1 Factor tree", str(self.tree_rows),
             "Active factor rows — what the project set out to collect", "—"],
            ["2.1 Mapped", str(self.tree_mapped),
             "Factor rows a published asset actually covers",
             f"{self.tree_mapped - self.tree_rows:+d} not covered by any asset"
             + (f", of which {self.tree_ignored} explicitly ignored" if self.tree_ignored else "")],
            ["2.2 Scored", str(self.scored_quality),
             "Distinct (L1–L4 × metric) groups in the assembled data",
             self._supply_note()],
            ["2.4 Scored", str(self.scored_statistical),
             "Driver indicators still in play after earlier verdicts",
             self._stat_note()],
        ]
        return out

    def _supply_note(self) -> str:
        bits: list[str] = []
        if self.supplied_unclaimed:
            bits.append(f"{self.supplied_unclaimed} supplied metric(s) match no factor row "
                        "(scored anyway — they are real data)")
        if self.quality_inherited:
            bits.append(f"{self.quality_inherited} skipped, already rejected at 2.1")
        bits.append("counts the data supplied, not the tree declared — the two are "
                    "different populations")
        return "; ".join(bits)

    def _stat_note(self) -> str:
        delta = self.scored_statistical - self.scored_quality
        bits = [f"{delta:+d} vs 2.2"]
        if self.stat_response:
            bits.append(f"{self.stat_response} response (KPI) series — not candidate drivers")
        if self.stat_inherited:
            bits.append(f"{self.stat_inherited} already rejected at 2.1/2.2/2.3")
        if self.stat_no_variance:
            bits.append(f"{self.stat_no_variance} constant across the whole panel")
        return "; ".join(bits)

    def sheet(self) -> dict:
        return {"name": "Reconciliation", "columns": RECONCILE_COLUMNS, "rows": self.rows()}


def build(st) -> Reconciliation:
    """Derive the population chain for a project. Never raises — a partial answer
    beats an artifact that cannot render."""
    from app.agents.dataset_cache import model_df, model_objects
    from app.agents.ledger import _matches, _norm_pair, drops_before
    from app.agents.stat_scoring import _indicator_panel
    from app.dataeng.mapping import resolve_factor_map
    from app.mmm.pivot import _is_y_row

    tree_rows = tree_mapped = tree_ignored = 0
    claimed: set[tuple[str, str]] = set()
    try:
        fmap = resolve_factor_map(st)
        tree_rows = len(fmap.rows)
        tree_mapped = sum(1 for r in fmap.rows if r.status == "mapped")
        tree_ignored = sum(1 for r in fmap.rows if r.status == "ignored")
        for r in fmap.rows:
            for name in (r.metric, r.indicator):
                if name:
                    claimed.add(_norm_pair(r.l4, name))
    except Exception:  # noqa: BLE001
        pass

    supplied = supplied_unclaimed = quality_inherited = 0
    stat_response = 0
    try:
        df = model_df(st)
        if not df.empty:
            y_mask = _is_y_row(df)
            groups = df.groupby(["l1", "l2", "l3", "l4", "metric"], dropna=False)
            inherited = drops_before(st, "quality")
            for (_l1, _l2, _l3, l4, metric), grp in groups:
                if not str(metric).strip() or str(metric) == "<NA>":
                    continue
                supplied += 1
                key = _norm_pair(l4, metric)
                if key not in claimed:
                    supplied_unclaimed += 1
                if inherited and _matches(key, inherited):
                    quality_inherited += 1
                if bool(y_mask.loc[grp.index].all()):
                    stat_response += 1
    except Exception:  # noqa: BLE001
        pass

    scored_quality = max(supplied - quality_inherited, 0)

    scored_stat = stat_inherited = no_variance = 0
    try:
        df = model_df(st)
        metas, wide, _y = _indicator_panel(st, df, model_objects(st))
        panel_keys = {_norm_pair(m["l4"], m["indicator"]) for m in metas}
        inherited_s = drops_before(st, "statistical")
        scored_stat = sum(1 for m in metas
                          if not _matches(_norm_pair(m["l4"], m["indicator"]), inherited_s))
        stat_inherited = len(metas) - scored_stat
        # Anything supplied and not a response that never reached the panel had no
        # usable variance in it (or no model object to sit in).
        no_variance = max(scored_quality - stat_response - len(metas), 0)
    except Exception:  # noqa: BLE001
        pass

    return Reconciliation(
        tree_rows=tree_rows, tree_mapped=tree_mapped, tree_ignored=tree_ignored,
        supplied_groups=supplied, supplied_unclaimed=supplied_unclaimed,
        scored_quality=scored_quality, quality_inherited=quality_inherited,
        scored_statistical=scored_stat, stat_response=stat_response,
        stat_inherited=stat_inherited, stat_no_variance=no_variance,
    )
