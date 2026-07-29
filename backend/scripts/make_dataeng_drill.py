"""Build a hand-runnable Data Engine + Data Intake drill from the real 2.32 dataset.

The seeded reference case arrives already published: its data assets are written
straight into ``ProjectState`` with ``status="published"``, so nothing in the Data
Engine's actual path — read raw files, wire transform steps, compile, ``dbt build``,
publish — is ever executed. ``make_synthetic_case.py`` does the same. That makes
both useless for answering "does the Data Engine work end to end, and does what it
publishes survive into Data Intake & Validation?".

This builds the opposite: **nothing is published**. It writes a folder of raw source
files that are deliberately *wrong* in the specific ways the typed transform steps
exist to fix, and seeds a project whose Business Understanding runs for real on the
genuine reference documents (the actual Scope workbook and the twelve real interview
transcripts — not the 500-character stand-ins the seeded case ships).

Every number comes from ``reference/02.数据智能体/【MMM AI】数据智能体-model
input_2.32.xlsx``. The truth table is carved from it, then shattered into five source
groups, one per defect:

    01 销量          4 files, one schema, three spellings per channel and a
                     different metric name in each   → union + enum_map ×2
    02 品牌媒体      abbreviated English headers, money as comma-separated text,
                     no channel column at all         → field_map (rename + expr cast)
    03 电商          platform and province names that only a lookup sheet resolves
                                                      → join ×2 + aggregate
    04 线下促销周报   weekly × SKU grain, test rows and returns mixed in
                                                      → filter + derive + aggregate
    05 门店执行与外部  monthly and tidy — only the column names are in the way
                                                      → field_map

Two of the factor paths (电商站内投流 and 促销优惠) have no name in the beverage
factor-tree template, so they publish as orphans and have to be adopted or
dismissed; and 促销优惠 · 花费 is split across groups 03 and 05 by channel, so one
factor row ends up supplied by two assets.

``_truth/truth_long_table.csv`` is the answer key: what a correct set of pipelines
must reproduce. ``verify_dataeng_drill.py`` checks a published project against it.

    PYTHONPATH=. .venv/bin/python scripts/make_dataeng_drill.py
    PYTHONPATH=. .venv/bin/python scripts/make_dataeng_drill.py --with-raw-uploads
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ID = "mizone-dataeng-drill"
PROJECT_NAME = "脉动 MMM · Data Engine 演练"
BRAND = "MIZONE"
INDUSTRY = ("food-bev", "beverage", "functional-drink")
KPI = "本品销量箱数"

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
REF = REPO / "reference"
SRC_XLSX = REF / "02.数据智能体" / "【MMM AI】数据智能体-model input_2.32.xlsx"
OUT_DIR = REPO / "test-data" / "dataeng-drill"

CHANNELS = ("MT", "TT", "EC")
BRANDS_KEPT = ("MIZONE", "16个竞品", "")

# The response arrives under a different name in every channel's system — the
# single most common real-world reason a union alone is not enough.
Y_SOURCE_METRIC = {"MT": "谈判点出货箱数", "TT": "Compass完成箱数", "EC": "Volume"}
Y_PATH = ("KPI", "KPI", "KPI", "本品销量")

# (l1, l3, l4, metric) → (role, source unit, scope, raw source group). l2 is read
# back off the reference rows so the factor path stays genuine.
#
# ``unit`` is not decoration. 已投放冰柜个数 appears in the reference under two
# METRICS 类型 — 个数 (a cabinet count) and RMB (what the cabinets cost) — and
# nothing but the unit tells them apart. Summing the two together is the same
# class of mistake as adding °C to RMB.
#
# ``scope`` decides what a blank 渠道类型 means. For a channel driver it is a
# sparse national roll-up that would double-count the per-channel detail, so it
# is dropped; for media it is the whole point — bought once for the country and
# shared into every model object.
DRIVERS: list[tuple[tuple[str, str, str, str], str, str, str, str]] = [
    (("渠道成交驱动", "店内促销", "旺点促销", "花费"),
     "spending", "RMB", "channel", "04_weekly"),
    (("渠道成交驱动", "品牌显现及陈列展示", "品牌显现（Store Decoration）", "花费"),
     "spending", "RMB", "channel", "04_weekly"),

    (("渠道成交驱动", "冰柜", "自有冰柜", "已投放冰柜个数"),
     "X", "个数", "channel", "05_store"),
    (("渠道成交驱动", "店内促销", "旺点促销", "执行门店数"),
     "X", "执行门店数", "channel", "05_store"),
    (("渠道成交驱动", "品牌显现及陈列展示", "品牌显现（Store Decoration）", "执行门店"),
     "X", "门店数量", "channel", "05_store"),
    (("渠道成交驱动", "渠道执行", "销售业代对于产品陈列的执行 - 数量多",
      "销售业代稽查平均门店整体排面数"), "X", "平均数", "channel", "05_store"),
    (("渠道成交驱动", "渠道执行", "销售业代对于产品陈列的执行 - 位置好",
      "销售业代稽查视平线达成率"), "X", "达成率", "channel", "05_store"),
    (("促销优惠", "促销优惠", "促销优惠", "PPI"), "X", "百分比", "channel", "05_store"),
    (("生意基本盘", "动销", "价格变动", "本品标价"), "X", "RMB", "channel", "05_store"),

    (("生意基本盘", "品类趋势", "季节性趋势", "温度"),
     "X", "Temperature", "national", "05_store"),
    (("生意基本盘", "竞争格局", "竞品消费者需求驱动变化", "竞品品牌媒体花费"),
     "X", "RMB", "national", "05_store"),
    (("生意基本盘", "竞争格局", "竞品渠道扩张", "竞品ND"),
     "X", "百分比", "national", "05_store"),

    (("消费者需求驱动", "品牌传播", "OTT", "花费"),
     "spending", "花费", "national", "02_media"),
    (("消费者需求驱动", "品牌传播", "Digital Display", "花费"),
     "spending", "花费", "national", "02_media"),
    (("消费者需求驱动", "品牌传播", "OOH", "花费"),
     "spending", "花费", "national", "02_media"),
    (("消费者需求驱动", "品牌传播", "热剧", "花费"),
     "spending", "花费", "national", "02_media"),
    (("消费者需求驱动", "社交媒体及线下路演", "社媒", "社媒活动互动量"),
     "X", "社媒活动互动量", "national", "02_media"),

    (("消费者需求驱动", "电商站内投流", "站内投流", "花费"),
     "spending", "花费", "channel", "03_ec"),
    # Deliberately split across two source groups by channel: its EC rows arrive
    # in the e-commerce workbook, its MT rows in the store-execution one. One
    # factor row supplied by several assets is a documented product case, and
    # nothing else in the drill exercises it.
    (("促销优惠", "促销优惠", "促销优惠", "花费"),
     "spending", "花费", "channel", "03_ec"),
]

# Metrics that are a level, not a flow: re-aggregating them means averaging.
# Keyed on the aligned (post-``ALIGN_METRIC``) name.
MEAN_METRICS = frozenset({
    "销售业代平均门店整体排面数", "销售业代视平线达成率", "PPI",
    "本品标价", "温度", "竞品ND",
})

# The 2.32 data file and the beverage factor-tree template were authored
# separately and disagree on wording: the data says 渠道/终端营销 where the tree
# says 渠道, and calls a metric 销售业代稽查视平线达成率 where the tree calls it
# 销售业代视平线达成率. Reconciling those is not what this drill is testing — task
# 1.5 emits a per-L4 data-request workbook precisely so returned data arrives on
# the agreed taxonomy — so the raw files are written on the tree's wording.
ALIGN_L2 = {
    "品牌广告/内容种草": "品牌广告",
    "渠道/终端营销": "渠道",
    "渠道执行": "渠道执行及运营",
}
ALIGN_METRIC = {
    "销售业代稽查平均门店整体排面数": "销售业代平均门店整体排面数",
    "销售业代稽查视平线达成率": "销售业代视平线达成率",
    "执行门店": "执行门店数",
}

# Two factor paths are deliberately left on the *data* file's wording, because
# something has to arrive unmatched or the orphan flow is untested. The template
# files 电商站内投流 as an L4 under 电商平台媒体及促销, and splits promotions into
# 组合优惠 / 单品折扣 rather than a flat 促销优惠 — so both land as orphans and
# have to be adopted into the tree or dismissed by hand.
ORPHAN_L3 = ("电商站内投流", "促销优惠")

DIM_COLS = ["品牌", "省份组别", "渠道类型", "渠道", "数据源", "METRICS类型", "METRICS"] + [
    f"数据类型Level{i}" for i in range(1, 9)]

# Real S1 material, reused verbatim. The competitor benchmark PDF is password
# protected and does not extract, so it is deliberately absent.
S1_UPLOADS: dict[str, list[str]] = {
    "project_background": [
        "01.商业智能体/【MMM AI】商业智能体-Scope_1.0.xlsx",
    ],
    "industry_reference": [
        "01.商业智能体/【MMM AI】商业智能体-行业知识_1.1.xlsx",
        "01.商业智能体/【MMM AI】商业智能体-factor&data_request_1.2.xlsx",
    ],
}
INTERVIEW_DIR = "01.商业智能体/【MMM AI】商业智能提-访谈框架及纪要_1.32/纪要"


# ── the truth table ──────────────────────────────────────
def _read_reference() -> pd.DataFrame:
    """The reference long table with every dimension column a clean string.

    pandas 3's ``str`` dtype keeps missing values as float NaN rather than the
    literal ``"nan"``, so the fill has to happen before anything strips or
    compares — otherwise the column stays mixed-type and every grouping breaks.
    """
    raw = pd.read_excel(SRC_XLSX, sheet_name="D.Data Station")
    df = pd.DataFrame(
        {c: raw[c].astype(str).fillna("").str.strip() for c in DIM_COLS})
    df = df.replace({"nan": "", "NA": "", "None": "", "#N/A": ""})
    df["value"] = pd.to_numeric(raw["VALUE"], errors="coerce")
    df["month"] = pd.to_numeric(raw["月"], errors="coerce")
    df = df.dropna(subset=["value", "month"])
    df["month"] = df["month"].astype(int)
    df["year"] = df["month"] // 100
    return df


def _collapse(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (brand, region, channel, month, factor path, metric)."""
    keys = ["brand", "province_group", "channel_type", "year", "month",
            "l1", "l2", "l3", "l4", "metric_type", "metric"]
    flows = df[~df["metric"].isin(MEAN_METRICS)].groupby(keys, as_index=False)["value"].sum()
    levels = df[df["metric"].isin(MEAN_METRICS)].groupby(keys, as_index=False)["value"].mean()
    out = pd.concat([flows, levels], ignore_index=True)
    out["value"] = out["value"].round(4)
    return out.sort_values(keys).reset_index(drop=True)


def build_truth() -> pd.DataFrame:
    ref = _read_reference()
    picked: list[pd.DataFrame] = []

    # Response — renamed onto one canonical metric, which is what the enum_map
    # step in source group 01 has to reproduce.
    for channel, source_metric in Y_SOURCE_METRIC.items():
        sel = ref[(ref["数据类型Level1"] == "KPI")
                  & (ref["渠道类型"] == channel)
                  & (ref["METRICS"] == source_metric)].copy()
        if sel.empty:
            raise SystemExit(f"reference has no {channel} response {source_metric!r}")
        picked.append(pd.DataFrame({
            "brand": BRAND, "province_group": sel["省份组别"],
            "channel_type": channel, "year": sel["year"], "month": sel["month"],
            "l1": Y_PATH[0], "l2": Y_PATH[1], "l3": Y_PATH[2], "l4": Y_PATH[3],
            "metric_type": "Y", "metric": KPI, "value": sel["value"],
            "group": "01_sales",
        }))

    for (l1, l3, l4, metric), role, unit, scope, group in DRIVERS:
        sel = ref[(ref["数据类型Level1"] == l1) & (ref["数据类型Level3"] == l3)
                  & (ref["数据类型Level4"] == l4) & (ref["METRICS"] == metric)
                  & (ref["METRICS类型"] == unit)]
        keep = CHANNELS if scope == "channel" else ("",)
        sel = sel[sel["渠道类型"].isin(keep) & sel["品牌"].isin(BRANDS_KEPT)]
        if sel.empty:
            raise SystemExit(
                f"reference has no {scope}/{unit} rows for {l1} > {l3} > {l4} > {metric}")
        l2 = sel["数据类型Level2"].map(lambda v: ALIGN_L2.get(v, v))
        picked.append(pd.DataFrame({
            "brand": sel["品牌"], "province_group": sel["省份组别"],
            "channel_type": sel["渠道类型"], "year": sel["year"], "month": sel["month"],
            "l1": l1, "l2": l2, "l3": l3, "l4": l4,
            "metric_type": role, "metric": ALIGN_METRIC.get(metric, metric),
            "value": sel["value"], "group": group,
        }))

    df = pd.concat(picked, ignore_index=True)
    groups = df[["l1", "l2", "l3", "l4", "metric", "group"]].drop_duplicates()
    truth = _collapse(df.drop(columns=["group"]))
    return truth.merge(groups, on=["l1", "l2", "l3", "l4", "metric"], how="left")


# ── raw source groups ────────────────────────────────────
def _split(value: float, weights: list[float]) -> list[float]:
    """Split a value by ``weights``, giving the remainder to the last piece.

    The pieces have to add back to exactly what came in — the whole point of the
    aggregate steps downstream is that summing the raw file reproduces the truth
    table, and a rounding drift would make a correct pipeline look wrong.
    """
    total = sum(weights)
    parts = [round(value * w / total, 6) for w in weights[:-1]]
    return parts + [round(value - sum(parts), 6)]


def _weeks_in(month: int) -> list[str]:
    """The Mondays that fall inside a yyyymm month."""
    start = pd.Timestamp(year=month // 100, month=month % 100, day=1)
    end = start + pd.offsets.MonthEnd(0)
    return [d.strftime("%Y-%m-%d")
            for d in pd.date_range(start, end, freq="W-MON")] or [start.strftime("%Y-%m-%d")]


def write_sales(truth: pd.DataFrame, out: Path) -> list[str]:
    """01 · one response, four files, three spellings and three metric names.

    Every channel's system calls the response something different and spells its
    own name inconsistently. Union alone produces a table whose channel column has
    eight distinct values for three channels — the enum_map steps are what make it
    modellable.
    """
    d = truth[truth["group"] == "01_sales"].copy()
    # How each file spells its channel: the first spelling is the common one, the
    # rest are the drift a real export accumulates.
    spellings = {
        "MT": ["现代渠道", "MT", "Modern Trade", "MT "],
        "TT": ["传统渠道", "TT", "Traditional Trade"],
        "EC": ["电商", "EC", "E-Commerce"],
    }

    def shape(sub: pd.DataFrame, channel: str, offset: int = 0) -> pd.DataFrame:
        opts = spellings[channel]
        # Deterministic drift: most rows get the primary spelling, a repeating
        # minority get the variants.
        chan = [opts[0] if (i + offset) % 7 else opts[1 + (i + offset) % (len(opts) - 1)]
                for i in range(len(sub))]
        return pd.DataFrame({
            "年": sub["year"].to_numpy(),
            "年月": sub["month"].to_numpy(),
            "品牌": sub["brand"].to_numpy(),
            "省份组别": sub["province_group"].to_numpy(),
            "渠道": chan,
            "指标名称": Y_SOURCE_METRIC[channel],
            "数值": sub["value"].to_numpy(),
        })

    mt = d[d["channel_type"] == "MT"].sort_values(["month", "province_group"])
    files: list[str] = []
    root = out / "01_销量"
    root.mkdir(parents=True, exist_ok=True)

    early = shape(mt[mt["year"] == 2023], "MT")
    late = shape(mt[mt["year"] >= 2024], "MT", offset=3)
    early.to_csv(root / "A1_sales_MT2023_销量.csv", index=False, encoding="utf-8-sig")
    late.to_csv(root / "A2_sales_MT2024_2025_销量.csv", index=False, encoding="utf-8-sig")
    shape(d[d["channel_type"] == "TT"].sort_values(["month", "province_group"]),
          "TT").to_excel(root / "A3_sales_TT_销量.xlsx", index=False, sheet_name="出货")
    shape(d[d["channel_type"] == "EC"].sort_values(["month"]),
          "EC").to_excel(root / "A4_sales_EC_销量.xlsx", index=False, sheet_name="GMV")
    files += ["A1_sales_MT2023_销量.csv", "A2_sales_MT2024_2025_销量.csv",
              "A3_sales_TT_销量.xlsx", "A4_sales_EC_销量.xlsx"]
    return files


def write_media(truth: pd.DataFrame, out: Path) -> list[str]:
    """02 · abbreviated English headers, money as text, and no channel column."""
    d = truth[truth["group"] == "02_media"].sort_values(["month", "l4"])
    root = out / "02_品牌媒体"
    root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({
        "yr": d["year"].to_numpy(),
        "mnth": d["month"].to_numpy(),
        "factor_l3": d["l3"].to_numpy(),
        "media_type": d["l4"].to_numpy(),
        "region": d["province_group"].to_numpy(),
        "metric_nm": d["metric"].to_numpy(),
        # Money the way a finance export writes it: text, thousands separators.
        "spend_txt": [f"{v:,.2f}" for v in d["value"]],
    })
    frame.to_excel(root / "B_media_品牌媒体投放明细.xlsx", index=False, sheet_name="media")
    return ["B_media_品牌媒体投放明细.xlsx"]


def write_ec(truth: pd.DataFrame, out: Path) -> list[str]:
    """03 · platform-level rows that only a lookup sheet can resolve to a channel."""
    d = truth[(truth["group"] == "03_ec") & (truth["channel_type"] == "EC")]
    d = d.sort_values(["month", "l4"])
    root = out / "03_电商"
    root.mkdir(parents=True, exist_ok=True)

    platforms = [("天猫", 0.5), ("京东", 0.3), ("抖音", 0.2)]
    rows = []
    for r in d.itertuples(index=False):
        for (name, _), part in zip(platforms, _split(r.value, [w for _, w in platforms])):
            # The two factors in this workbook sit under different L1/L2, so the
            # path travels with the row rather than being a constant in the
            # field_map — a workbook that mixes factors usually does carry it.
            rows.append({"年月": r.month, "平台": name, "省份组别": r.province_group,
                         "因子L1": r.l1, "因子L2": r.l2, "因子L3": r.l3,
                         "因子L4": r.l4, "指标": r.metric, "金额": part})
    detail = pd.DataFrame(rows)

    lookup = pd.DataFrame([
        {"平台": "天猫", "渠道类型": "EC", "渠道": "天猫旗舰店"},
        {"平台": "京东", "渠道类型": "EC", "渠道": "京东自营"},
        {"平台": "抖音", "渠道类型": "EC", "渠道": "抖音小店"},
        # Present in the lookup but never in the detail — a join must not invent
        # rows for it.
        {"平台": "拼多多", "渠道类型": "EC", "渠道": "拼多多旗舰店"},
    ])
    path = root / "C_ecom_电商投流与促销.xlsx"
    with pd.ExcelWriter(path) as writer:
        detail.to_excel(writer, index=False, sheet_name="detail_明细")
        lookup.to_excel(writer, index=False, sheet_name="lookup_平台对照表")
    return ["C_ecom_电商投流与促销.xlsx"]


def write_weekly(truth: pd.DataFrame, out: Path) -> list[str]:
    """04 · weekly × SKU grain with test rows and returns mixed in."""
    d = truth[truth["group"] == "04_weekly"].sort_values(["month", "channel_type"])
    root = out / "04_线下促销周报"
    root.mkdir(parents=True, exist_ok=True)

    skus = [("MZ-500ML", 0.65), ("MZ-1L", 0.35)]
    rows = []
    for i, r in enumerate(d.itertuples(index=False)):
        weeks = _weeks_in(int(r.month))
        for sku, sku_part in zip([s for s, _ in skus],
                                 _split(r.value, [w for _, w in skus])):
            for week, part in zip(weeks, _split(sku_part, [1.0] * len(weeks))):
                rows.append({"week_start": week, "channel_type": r.channel_type,
                             "province_group": r.province_group, "sku": sku,
                             "factor_l3": r.l3, "factor_l4": r.l4,
                             "metric_name": r.metric, "value": part, "is_test": "N"})
        # Rows a real export leaves in: a UAT row and a returns reversal. Both
        # must be filtered out, and neither is distinguishable by value alone.
        if i % 23 == 0:
            rows.append({"week_start": weeks[0], "channel_type": r.channel_type,
                         "province_group": r.province_group, "sku": "TEST-SKU",
                         "factor_l3": r.l3, "factor_l4": r.l4,
                         "metric_name": r.metric, "value": 999999.0, "is_test": "Y"})
        if i % 31 == 0:
            rows.append({"week_start": weeks[-1], "channel_type": r.channel_type,
                         "province_group": r.province_group, "sku": "MZ-500ML",
                         "factor_l3": r.l3, "factor_l4": r.l4,
                         "metric_name": r.metric, "value": -abs(round(r.value * 0.05, 2)),
                         "is_test": "N"})
    frame = pd.DataFrame(rows)
    frame.to_csv(root / "D_weekly_线下促销周报.csv", index=False, encoding="utf-8-sig")
    return ["D_weekly_线下促销周报.csv"]


def write_store(truth: pd.DataFrame, out: Path) -> list[str]:
    """05 · monthly and already tidy — only the column names are in the way."""
    d = truth[(truth["group"] == "05_store")
              | ((truth["group"] == "03_ec") & (truth["channel_type"] != "EC"))]
    d = d.sort_values(["month", "l3", "l4", "metric"])
    root = out / "05_门店执行与外部因子"
    root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({
        "年": d["year"].to_numpy(), "年月": d["month"].to_numpy(),
        "品牌": d["brand"].to_numpy(), "省份组别": d["province_group"].to_numpy(),
        "渠道类型": d["channel_type"].to_numpy(),
        "因子L1": d["l1"].to_numpy(), "因子L2": d["l2"].to_numpy(),
        "因子L3": d["l3"].to_numpy(), "因子L4": d["l4"].to_numpy(),
        "指标": d["metric"].to_numpy(), "指标角色": d["metric_type"].to_numpy(),
        "数值": d["value"].to_numpy(),
    })
    frame.to_excel(root / "E_store_门店执行与外部因子.xlsx", index=False, sheet_name="monthly")
    return ["E_store_门店执行与外部因子.xlsx"]


WRITERS = (write_sales, write_media, write_ec, write_weekly, write_store)


def write_raw_files(truth: pd.DataFrame, out: Path) -> dict[str, list[str]]:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    produced = {w.__name__.removeprefix("write_"): w(truth, out) for w in WRITERS}
    truth_dir = out / "_truth"
    truth_dir.mkdir(exist_ok=True)
    truth.to_csv(truth_dir / "truth_long_table.csv", index=False, encoding="utf-8-sig")
    return produced


# ── project seeding ──────────────────────────────────────
def _s1_documents() -> list[tuple[str, Path]]:
    """(category, path) for every real reference document S1 grounds on."""
    picked: list[tuple[str, Path]] = []
    for category, names in S1_UPLOADS.items():
        for name in names:
            path = REF / name
            if path.exists():
                picked.append((category, path))
    minutes = REF / INTERVIEW_DIR
    if minutes.is_dir():
        for path in sorted(minutes.glob("*.docx")):
            if not path.name.startswith("~$"):
                picked.append(("interview_minutes", path))
    return picked


def seed(project_id: str, raw_files: dict[str, list[str]],
         upload_raw: bool = False, reset: bool = False) -> dict:
    """Create the project and upload the real S1 material. Nothing is published.

    S1 is left to run for real against these documents — the point of the drill is
    that the factor tree the Data Engine maps onto was actually derived, not
    written into the state file by this script.

    Seeding an existing project throws away that derivation: ``initial_state``
    returns a blank blackboard, so the whole Business-Understanding run — and the
    factor tree every later step maps onto — is gone with no warning. Re-running
    this script to regenerate the raw files therefore refuses to touch a project
    that already exists unless ``reset`` is explicit.
    """
    from app.domain.models import IndustryRef, ProjectMeta
    from app.store.files import get_files
    from app.store.state import get_store, initial_state

    store = get_store()
    if not reset and store.get(project_id) is not None:
        return {"projectId": project_id, "uploaded": {}, "skipped": True}
    meta = ProjectMeta(
        id=project_id, name=PROJECT_NAME, brand=BRAND,
        industry=IndustryRef(l1=INDUSTRY[0], l2=INDUSTRY[1], l3=INDUSTRY[2]),
        kpi=KPI,
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    st = initial_state(meta)
    store._states[project_id] = st  # noqa: SLF001 — same seeding path as the reference case
    store._upsert_index(meta)       # noqa: SLF001

    files = get_files()
    files.purge(project_id)
    uploaded: dict[str, list[str]] = {}
    for category, path in _s1_documents():
        record = files.add(project_id, category, path.name, path.read_bytes())
        uploaded.setdefault(category, []).append(
            f"{record.filename} ({record.parse_chars} chars"
            + ("" if record.parsed else f", PARSE FAILED: {record.parse_error}") + ")")

    if upload_raw:
        for group, names in raw_files.items():
            folder = next(p for p in OUT_DIR.iterdir()
                          if p.is_dir() and p.name.endswith(_GROUP_DIR[group]))
            for name in names:
                files.add(project_id, "raw_data", name, (folder / name).read_bytes())
        uploaded["raw_data"] = [n for names in raw_files.values() for n in names]

    store.save(project_id)
    return {"projectId": project_id, "uploaded": uploaded}


_GROUP_DIR = {"sales": "销量", "media": "品牌媒体", "ec": "电商",
              "weekly": "线下促销周报", "store": "门店执行与外部因子"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-id", default=PROJECT_ID)
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--files-only", action="store_true",
                    help="write the raw data folder without touching any project")
    ap.add_argument("--with-raw-uploads", action="store_true",
                    help="also upload the raw files into the project's Data Engine "
                         "inbox (skips the drag-and-drop the guide asks for)")
    ap.add_argument("--reset", action="store_true",
                    help="wipe and re-seed the project even if it exists — this "
                         "DISCARDS any Business Understanding run and its factor tree")
    args = ap.parse_args()

    out = Path(args.out)
    truth = build_truth()
    produced = write_raw_files(truth, out)

    print(f"truth: {len(truth)} rows · {truth['month'].nunique()} months "
          f"({truth['month'].min()}–{truth['month'].max()}) · "
          f"{len(truth[['l4', 'metric']].drop_duplicates())} indicators")
    for group, names in produced.items():
        print(f"  {group:8s} {', '.join(names)}")
    print(f"written to {out}")

    if args.files_only:
        return
    result = seed(args.project_id, produced,
                  upload_raw=args.with_raw_uploads, reset=args.reset)
    if result.get("skipped"):
        print(f"\nproject {args.project_id} already exists — left untouched.")
        print("Raw files above are refreshed; pass --reset to re-seed the project "
              "(this discards its Business Understanding run and factor tree).")
        return
    print(f"\nproject {result['projectId']} seeded — S1 not run, nothing published")
    for category, names in result["uploaded"].items():
        print(f"  {category}: {len(names)} file(s)")
        for n in names:
            print(f"      {n}")


if __name__ == "__main__":
    main()
