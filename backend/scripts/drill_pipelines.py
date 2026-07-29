"""The five transform pipelines the drill's raw files need — the guide's answer key.

Each is exactly what a person is asked to wire by hand in the Data Engine, written
out as the ``TransformStep`` objects the editor produces. ``verify_dataeng_drill.py``
applies these and checks the published marts against ``_truth/truth_long_table.csv``,
so the guide can never ask for a pipeline that does not actually work.

Keep this in step with ``docs/testing/dataeng-drill-guide.md``: if a step's config
changes here, the guide's instructions for that step are wrong.
"""
from __future__ import annotations

from app.domain.models import (
    AggSpec,
    DeriveSpec,
    EnumMapEntry,
    FieldMapEntry,
    JoinConfig,
    TransformPipeline,
    TransformStep,
)

# Every mart lands on these target-schema columns. l5–l8 are optional and the
# compiler stamps `source` itself, so neither is mapped by hand.
Y_CONST = {"l1": "KPI", "l2": "KPI", "l3": "KPI", "l4": "本品销量",
           "metric_type": "Y", "metric": "本品销量箱数"}


def _fm(**cols: str) -> list[FieldMapEntry]:
    """field_map entries from ``target=source``; a value in 'quotes' is a constant."""
    out: list[FieldMapEntry] = []
    for target, source in cols.items():
        if source.startswith("'") or source.startswith("cast(") or "(" in source:
            out.append(FieldMapEntry(target=target, expr=source))
        else:
            out.append(FieldMapEntry(target=target, source=source))
    return out


# ── 01 销量 · union + two enum maps ──────────────────────
# The four exports share a schema but not a vocabulary: each channel's system
# spells its own name three ways and calls the response something different.
CHANNEL_SPELLINGS = {
    "MT": ["现代渠道", "MT", "Modern Trade", "MT "],
    "TT": ["传统渠道", "TT", "Traditional Trade"],
    "EC": ["电商", "EC", "E-Commerce"],
}
Y_SPELLINGS = {"本品销量箱数": ["谈判点出货箱数", "Compass完成箱数", "Volume"]}


def _enum(mapping: dict[str, list[str]]) -> list[EnumMapEntry]:
    return [EnumMapEntry(raw=raw, canonical=canonical, by="human", status="accepted")
            for canonical, raws in mapping.items() for raw in raws]


def sales_pipeline(sources: list[str]) -> TransformPipeline:
    return TransformPipeline(
        outputStep="s4_map",
        note="四份出货导出：先合并，再把渠道与指标名统一，最后落到目标表结构。",
        steps=[
            TransformStep(
                id="s1_union", kind="union", name="union sales",
                note="四个渠道/年份的导出列结构一致，直接纵向合并。",
                inputs=[f"source:{s}" for s in sources]),
            TransformStep(
                id="s2_channel", kind="enum_map", name="std channel",
                note="渠道列有 8 种写法，统一成 MT / TT / EC。",
                inputs=["s1_union"], enumField="渠道", enumTarget="channel_type",
                enumMap=_enum(CHANNEL_SPELLINGS)),
            TransformStep(
                id="s3_metric", kind="enum_map", name="std metric",
                note="每个渠道的系统对销量的叫法不同，统一成本品销量箱数。",
                inputs=["s2_channel"], enumField="指标名称", enumTarget="metric",
                enumMap=_enum(Y_SPELLINGS)),
            TransformStep(
                id="s4_map", kind="field_map", name="to target schema",
                note="改名到目标长表列，并补上 KPI 的因子路径常量。",
                inputs=["s3_metric"],
                fieldMap=_fm(brand="品牌", province_group="省份组别",
                             channel_type="渠道", year="年", month="年月",
                             metric="指标名称", value="数值",
                             **{k: f"'{v}'" for k, v in Y_CONST.items()
                                if k not in ("metric",)})),
        ])


# ── 02 品牌媒体 · one field_map that renames, casts and classifies ──
def media_pipeline(sources: list[str]) -> TransformPipeline:
    source = sources[0]
    return TransformPipeline(
        outputStep="m1_map",
        note="财务导出的媒体投放：英文缩写列名、金额是带千分位的文本、没有渠道列。",
        steps=[
            TransformStep(
                id="m1_map", kind="field_map", name="media to target",
                note="重命名列；金额去掉千分位再转 double；渠道留空表示全国投放。",
                inputs=[f"source:{source}"],
                fieldMap=[
                    FieldMapEntry(target="brand", expr="'MIZONE'"),
                    FieldMapEntry(target="province_group", source="region"),
                    # National media is bought once for the country: an empty
                    # channel is the signal that it belongs to every model object.
                    FieldMapEntry(target="channel_type", expr="''"),
                    FieldMapEntry(target="year", source="yr", cast="integer"),
                    FieldMapEntry(target="month", source="mnth", cast="integer"),
                    FieldMapEntry(target="l1", expr="'消费者需求驱动'"),
                    FieldMapEntry(target="l2", expr="'品牌广告'"),
                    FieldMapEntry(target="l3", source="factor_l3"),
                    FieldMapEntry(target="l4", source="media_type"),
                    FieldMapEntry(
                        target="metric_type",
                        expr="case when metric_nm = '花费' then 'spending' else 'X' end"),
                    FieldMapEntry(target="metric", source="metric_nm"),
                    FieldMapEntry(target="value",
                                  expr="cast(replace(spend_txt, ',', '') as double)"),
                ]),
        ])


# ── 03 电商 · join to a lookup sheet, then aggregate platforms away ──
def ecom_pipeline(sources: list[str]) -> TransformPipeline:
    # Pick the two sheets by name rather than by position: the workbook's sheet
    # order is not a contract, and wiring the lookup as the left side of the join
    # would quietly produce four rows instead of two hundred.
    detail = next(s for s in sources if "detail" in s)
    lookup = next(s for s in sources if "lookup" in s)
    return TransformPipeline(
        outputStep="e3_map",
        note="平台级明细：先用对照表把平台翻成渠道，再把平台汇总掉，最后落表。",
        steps=[
            TransformStep(
                id="e1_join", kind="join", name="platform lookup",
                note="明细只有平台名，渠道类型要从对照表带过来。",
                inputs=[f"source:{detail}", f"source:{lookup}"],
                join=JoinConfig(how="left", leftOn=["平台"], rightOn=["平台"],
                                rightColumns=["渠道类型"])),
            TransformStep(
                id="e2_agg", kind="aggregate", name="sum platforms",
                note="模型按渠道建，不按平台，所以把三个平台加总回渠道。",
                inputs=["e1_join"],
                groupBy=["年月", "渠道类型", "省份组别", "因子L1", "因子L2",
                         "因子L3", "因子L4", "指标"],
                aggs=[AggSpec(column="金额", func="sum", alias="金额")]),
            TransformStep(
                id="e3_map", kind="field_map", name="ecom to target",
                note="改名到目标列；年份从年月前四位取。",
                inputs=["e2_agg"],
                fieldMap=[
                    FieldMapEntry(target="brand", expr="'MIZONE'"),
                    FieldMapEntry(target="province_group", source="省份组别"),
                    FieldMapEntry(target="channel_type", source="渠道类型"),
                    FieldMapEntry(target="year", expr='cast("年月" / 100 as integer)'),
                    FieldMapEntry(target="month", source="年月", cast="integer"),
                    FieldMapEntry(target="l1", source="因子L1"),
                    FieldMapEntry(target="l2", source="因子L2"),
                    FieldMapEntry(target="l3", source="因子L3"),
                    FieldMapEntry(target="l4", source="因子L4"),
                    FieldMapEntry(target="metric_type", expr="'spending'"),
                    FieldMapEntry(target="metric", source="指标"),
                    FieldMapEntry(target="value", source="金额", cast="double"),
                ]),
        ])


# ── 04 线下促销周报 · filter the junk, derive a month, aggregate the grain up ──
def weekly_pipeline(sources: list[str]) -> TransformPipeline:
    source = sources[0]
    return TransformPipeline(
        outputStep="w4_map",
        note="周×SKU 的门店周报，夹着 UAT 行和退货冲销行；要先清掉再升到月粒度。",
        steps=[
            TransformStep(
                id="w1_filter", kind="filter", name="drop test & returns",
                note="is_test='Y' 是上线测试行，负数是退货冲销，两者都不进模型。",
                inputs=[f"source:{source}"],
                filterExpr="is_test <> 'Y' and value >= 0"),
            TransformStep(
                id="w2_month", kind="derive", name="week to month",
                note="按周起始日归属到 yyyymm。",
                inputs=["w1_filter"],
                derive=[DeriveSpec(
                    name="month",
                    expr="cast(strftime(cast(week_start as date), '%Y%m') as integer)")]),
            TransformStep(
                id="w3_agg", kind="aggregate", name="sum to month",
                note="把周和 SKU 两个维度加总掉，回到月×渠道×区域。",
                inputs=["w2_month"],
                groupBy=["month", "channel_type", "province_group",
                         "factor_l3", "factor_l4", "metric_name"],
                aggs=[AggSpec(column="value", func="sum", alias="value")]),
            TransformStep(
                id="w4_map", kind="field_map", name="weekly to target",
                note="改名到目标列并补上因子路径常量。",
                inputs=["w3_agg"],
                fieldMap=[
                    FieldMapEntry(target="brand", expr="'MIZONE'"),
                    FieldMapEntry(target="province_group", source="province_group"),
                    FieldMapEntry(target="channel_type", source="channel_type"),
                    FieldMapEntry(target="year", expr='cast("month" / 100 as integer)'),
                    FieldMapEntry(target="month", source="month", cast="integer"),
                    FieldMapEntry(target="l1", expr="'渠道成交驱动'"),
                    FieldMapEntry(target="l2", expr="'渠道'"),
                    FieldMapEntry(target="l3", source="factor_l3"),
                    FieldMapEntry(target="l4", source="factor_l4"),
                    FieldMapEntry(target="metric_type", expr="'spending'"),
                    FieldMapEntry(target="metric", source="metric_name"),
                    FieldMapEntry(target="value", source="value", cast="double"),
                ]),
        ])


# ── 05 门店执行与外部因子 · already tidy, only the headers are in the way ──
def store_pipeline(sources: list[str]) -> TransformPipeline:
    source = sources[0]
    return TransformPipeline(
        outputStep="t1_map",
        note="月度且干净的一张表，只需要把中文表头映射到目标列。",
        steps=[
            TransformStep(
                id="t1_map", kind="field_map", name="store to target",
                note="纯改名，没有口径变化。",
                inputs=[f"source:{source}"],
                fieldMap=_fm(brand="品牌", province_group="省份组别",
                             channel_type="渠道类型", year="年", month="年月",
                             l1="因子L1", l2="因子L2", l3="因子L3", l4="因子L4",
                             metric_type="指标角色", metric="指标", value="数值")),
        ])
