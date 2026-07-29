"""The model-object key space: one model per **channel × product**.

Decision 2026-07-27, superseding the 2026-07-23 national roll-up. S2 no longer
aggregates anything before it screens or fits:

* the two scorecards (2.2 quality, 2.4 statistical) read the assembled long table
  exactly as it was published — see ``app.agents.stat_scoring`` for what that does
  to the panel the tests run on;
* the OLS stage fits **one model per ``(channel_type, brand)`` combination that
  carries a response** — N channels × M products = N×M models.

An object id is ``f"{channel_type}{OBJECT_SEP}{brand}"``. An id with no separator
is read as a bare ``channel_type``: that is the pre-2026-07-27 shape (including
the legacy ``TOTAL`` object and the ``'+'`` channel-union syntax), so an
``OlsConfig`` saved before this change still resolves against the same rows.
Everything downstream — ``ModelSelection``, ``OlsConfig``, the ``olsTree`` body,
the React view — treats the id as an opaque string, which is why widening it
needs no change there.

**Market rows are shared, not partitioned.** A brand that carries no response —
the competitor aggregate, a category total, or simply blank on generic national
spend — cannot be a model object, but its spend and activity are genuine drivers
of every product's sales in that channel. Those rows are therefore visible to
every product model in their channel rather than being split off into a model
that could never be fitted. Without this, moving from one national model to
per-product models would silently delete the competitive drivers from every fit.
"""
from __future__ import annotations

import weakref

import pandas as pd

# Machine separator inside a model-object id. Deliberately not "|" (the artifact
# row keys are f"{object}|{l4}|{metric}") and not "+" (the channel-union syntax).
OBJECT_SEP = "::"
# What a reader sees instead of the separator.
LABEL_SEP = " · "

__all__ = [
    "OBJECT_SEP",
    "LABEL_SEP",
    "make_object",
    "split_object",
    "object_label",
    "response_brands",
    "object_mask",
    "enumerate_objects",
]


def _clean(v: object) -> str:
    """A dimension value as a comparable string ("" for blank/NA)."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("", "nan", "<na>", "none") else s


def _clean_col(df: pd.DataFrame, col: str) -> pd.Series:
    """``df[col]`` normalized to stripped strings, "" where absent or blank."""
    if col not in df.columns:
        return pd.Series("", index=df.index, dtype="object")
    s = df[col].astype("string").str.strip()
    s = s.where(s.notna() & s.ne("") & s.str.lower().ne("nan"), "")
    return s.astype("object")


def make_object(channel_type: object, brand: object = "") -> str:
    """The object id for one (channel, product) cell.

    A blank brand yields the bare channel_type — a project whose upload carries
    no product column keeps exactly the pre-2026-07-27 object ids, so its saved
    config and frozen gate verdicts still match.
    """
    ct, b = _clean(channel_type), _clean(brand)
    return f"{ct}{OBJECT_SEP}{b}" if ct and b else ct


def split_object(obj: object) -> tuple[str, str]:
    """``"MT::MIZONE"`` → ``("MT", "MIZONE")``; ``"MT"`` → ``("MT", "")``."""
    s = _clean(obj)
    if OBJECT_SEP not in s:
        return s, ""
    ct, brand = s.split(OBJECT_SEP, 1)
    return _clean(ct), _clean(brand)


def object_label(obj: object) -> str:
    """The id as a reader sees it: ``"MT · MIZONE"``."""
    ct, brand = split_object(obj)
    return f"{ct}{LABEL_SEP}{brand}" if brand else ct


# `response_brands` is asked of the same frame on every `object_mask` call, and it
# runs the Y predicate over the whole long table each time — the dominant cost of
# a 2.5 proposal before this. Keyed by frame identity and validated with a weak
# reference, so a recycled `id()` can never serve another frame's answer.
_BRANDS_CACHE: dict[tuple, tuple[weakref.ReferenceType, frozenset[str]]] = {}
_BRANDS_CACHE_MAX = 32


def _vocab(st=None):
    """The project's vocabulary, or the default when there is no project context.

    Object enumeration reads the taxonomy through this. Hardcoding the default
    meant a project whose Knowledge pack renames the L1 labels enumerated **zero**
    model objects — while `ols_review`, which is vocab-aware, went on reporting
    candidates for objects that did not exist. The two disagreed with no error.
    """
    from app.agents.vocabulary import DEFAULT_VOCAB, vocab_for
    if st is None:
        return DEFAULT_VOCAB
    try:
        return vocab_for(st)
    except Exception:  # noqa: BLE001
        return DEFAULT_VOCAB


def response_brands(df: pd.DataFrame, st=None) -> frozenset[str]:
    """Brands that carry a response (Y) — the products that can be modeled.

    Case-folded, so callers compare against ``brand.str.upper()``. Everything
    else in ``brand`` is *market* context (competitors, category totals, blanks):
    it can never be a model object, and its rows are shared — see the module note.
    """
    from app.mmm.pivot import _is_y_row

    if df is None or df.empty or "brand" not in df.columns:
        return frozenset()
    key = (id(df), id(st))
    hit = _BRANDS_CACHE.get(key)
    if hit is not None and hit[0]() is df:
        return hit[1]
    try:
        y = df[_is_y_row(df, _vocab(st))]
    except Exception:  # noqa: BLE001 — an untaggable table simply has no products
        return frozenset()
    out = frozenset(b.upper() for b in _clean_col(y, "brand") if b) if not y.empty \
        else frozenset()
    try:
        ref = weakref.ref(df)
    except TypeError:  # noqa: PERF203 — not weak-referenceable: answer, don't cache
        return out
    if len(_BRANDS_CACHE) >= _BRANDS_CACHE_MAX:
        _BRANDS_CACHE.clear()
    _BRANDS_CACHE[key] = (ref, out)
    return out


def object_mask(df: pd.DataFrame, model_object: str, st=None) -> pd.Series:
    """Rows belonging to ``model_object``: its own channel × product, plus every
    row bought for no single channel or claimed by no single product.

    Two kinds of row are **shared into every model**, and for the same reason —
    they drive all of them and belong to none:

    * **No ``channel_type``** — national media. TV, online video, influencer and
      search are bought once for the whole country; the retailer feed is what
      carries a channel. Requiring a channel here is what made per-channel
      modeling delete them: on the synthetic case it cut every model from 17
      drivers to 6, leaving four trade variables to explain sales that national
      media actually drove.
    * **A brand no product model can claim** — competitors, category totals, and
      rows left blank because the spend was not product-specific.

    ``channel_type`` still accepts the ``'+'`` union syntax (``"EC+O2O"``). An id
    with no brand half selects the whole channel, which is what every
    pre-2026-07-27 object id means.
    """
    ct_part, brand_part = split_object(model_object)
    parts = [p.strip().upper() for p in ct_part.split("+") if p.strip()]
    ct = _clean_col(df, "channel_type").str.upper()
    # `ct.eq("")` is the national row: not "missing data" to be tolerated, but a
    # real statement that this driver has no channel of its own.
    mask = (ct.isin(parts) | ct.eq("")) if parts else pd.Series(True, index=df.index)
    if not brand_part:
        return mask
    brand = _clean_col(df, "brand").str.upper()
    shared = ~brand.isin(response_brands(df, st))
    return mask & (brand.eq(brand_part.upper()) | shared)


def enumerate_objects(df: pd.DataFrame, st=None) -> list[str]:
    """Every ``(channel, product)`` cell the data can actually support a model for,
    busiest first.

    A cell qualifies when it carries **both** a response and at least one driver
    row in its own + shared-market slice. Both halves are required: a competitor
    brand's sell-out passes the first test and fails the second, and admitting it
    would produce a model object that can only ever report "no usable X drivers".
    :func:`skipped_objects` reports the near misses so they stay visible.
    """
    if df is None or df.empty:
        return []
    from app.mmm.pivot import _is_y_row, is_driver_row

    vocab = _vocab(st)
    try:
        y_mask = _is_y_row(df, vocab)
    except Exception:  # noqa: BLE001 — no recognisable taxonomy → no objects
        return []
    y = df[y_mask]
    if y.empty:
        return []

    ct_all = _clean_col(df, "channel_type")
    brand_all = _clean_col(df, "brand")
    drv_mask = is_driver_row(df, vocab) & ~y_mask

    counts = (pd.DataFrame({"ct": ct_all[y_mask], "brand": brand_all[y_mask]})
              .value_counts(["ct", "brand"], sort=True))

    out: list[str] = []
    for (ct, brand), _n in counts.items():
        if not ct:
            continue
        obj = make_object(ct, brand)
        if obj in out:
            continue
        # Ask the same question the fit will: does this object's own slice — its
        # channel × product plus the national and market rows it shares — carry a
        # driver? Testing it any other way lets the two disagree.
        if not bool((drv_mask & object_mask(df, obj, st)).any()):
            continue
        out.append(obj)
    return out


def skipped_objects(df: pd.DataFrame, st=None) -> list[str]:
    """``(channel, product)`` cells that carry a response but no drivers.

    These are real rows in the assembled table that cannot become a model — a
    competitor's sell-out with no competitor spend behind it, most often. Reported
    as a finding rather than dropped in silence.
    """
    if df is None or df.empty:
        return []
    from app.mmm.pivot import _is_y_row

    try:
        y_mask = _is_y_row(df, _vocab(st))
    except Exception:  # noqa: BLE001
        return []
    kept = set(enumerate_objects(df, st))
    ct_all = _clean_col(df, "channel_type")
    brand_all = _clean_col(df, "brand")
    seen: list[str] = []
    for ct, brand in zip(ct_all[y_mask], brand_all[y_mask]):
        if not ct:
            continue
        obj = make_object(ct, brand)
        if obj and obj not in kept and obj not in seen:
            seen.append(obj)
    return seen
