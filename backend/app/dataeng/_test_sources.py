"""Raw source naming is a contract — this pins it.

A pipeline step wires itself to ``source:<table>``. Before, a lone single-sheet
upload was named ``raw`` and everything was renamed the moment a second file
arrived, silently stranding every step that referenced it. These tests assert the
property that prevents that: a table's name depends only on its own (file, sheet).

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_sources``
"""
from __future__ import annotations

import io
import shutil

import pandas as pd

from app.config import get_settings
from app.dataeng.sources import (
    heal_pipeline_inputs, read_asset_sources, source_labels,
)
from app.domain.models import DataAsset, TransformPipeline, TransformStep
from app.store.files import get_files

PROJECT_ID = "_test_sources"


def _xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"channel": ["TMALL", "JD"], "value": [1.0, 2.0]})


def _upload(filename: str, content: bytes) -> str:
    return get_files().add(PROJECT_ID, "raw_data", filename, content).id


def _asset(*file_ids: str) -> DataAsset:
    return DataAsset(id="da-test", name="Test", status="raw", sourceFileIds=list(file_ids))


def test_names_are_stable_as_sources_are_added() -> None:
    """The regression: adding a second file must not rename the first table."""
    a = _upload("sales.xlsx", _xlsx({"Sheet1": _frame()}))
    names_alone = [m.name for m, _ in read_asset_sources(PROJECT_ID, _asset(a)).pairs]
    assert names_alone == ["sales"], names_alone

    b = _upload("spend.csv", b"channel,cost\nTMALL,10\n")
    both = read_asset_sources(PROJECT_ID, _asset(a, b))
    names_together = [m.name for m, _ in both.pairs]
    assert names_together == ["sales", "spend"], names_together
    assert names_alone[0] in names_together, "adding a source renamed an existing table"
    print(f"[stable] alone={names_alone} · together={names_together}")


def test_multi_sheet_is_namespaced_by_file() -> None:
    """Two workbooks sharing a sheet name must not collide into one table."""
    a = _upload("north.xlsx", _xlsx({"data": _frame()}))
    b = _upload("south.xlsx", _xlsx({"data": _frame()}))
    # Each workbook has one sheet, so the file stem alone identifies it...
    single = [m.name for m, _ in read_asset_sources(PROJECT_ID, _asset(a, b)).pairs]
    assert single == ["north", "south"], single

    c = _upload("east.xlsx", _xlsx({"jan": _frame(), "feb": _frame()}))
    multi = [m.name for m, _ in read_asset_sources(PROJECT_ID, _asset(c)).pairs]
    assert multi == ["east_jan", "east_feb"], multi
    print(f"[namespace] single-sheet={single} · multi-sheet={multi}")


def test_non_ascii_names_are_distinct_and_stable() -> None:
    """CJK filenames sanitize to nothing; they must still get distinct, repeatable
    identifiers rather than all collapsing onto the same one."""
    a = _upload("销售数据.xlsx", _xlsx({"表一": _frame()}))
    b = _upload("投放费用.xlsx", _xlsx({"表一": _frame()}))
    first = [m.name for m, _ in read_asset_sources(PROJECT_ID, _asset(a, b)).pairs]
    again = [m.name for m, _ in read_asset_sources(PROJECT_ID, _asset(a, b)).pairs]
    assert len(set(first)) == 2, first
    assert first == again, (first, again)
    print(f"[cjk] {first} (stable across reads)")


def test_unreadable_files_are_reported_not_swallowed() -> None:
    a = _upload("legacy.xls", b"\xd0\xcf\x11\xe0not-really-excel")
    read = read_asset_sources(PROJECT_ID, _asset(a))
    assert not read.pairs
    assert len(read.issues) == 1 and "xls" in read.issues[0].reason, read.issues
    read2 = read_asset_sources(PROJECT_ID, _asset("no-such-file"))
    assert read2.issues and "no longer" in read2.issues[0].reason, read2.issues
    print(f"[issues] {read.issues[0].reason}")


def test_source_labels_name_the_sheet_only_when_needed() -> None:
    """The label is what rows carry in `source` and what the Data module filters on.

    A single-sheet file keeps its bare filename: suffixing it would relabel the very
    same source and split it from its own already-published rows in that filter.
    """
    one = _upload("spend.xlsx", _xlsx({"Sheet1": _frame()}))
    many = _upload("regions.xlsx", _xlsx({"north": _frame(), "south": _frame()}))
    labels = source_labels(read_asset_sources(PROJECT_ID, _asset(one, many)))
    assert labels["spend"] == "spend.xlsx", labels
    assert labels["regions_north"] == "regions.xlsx › north", labels
    assert labels["regions_south"] == "regions.xlsx › south", labels
    assert len(set(labels.values())) == 3, labels
    print(f"[labels] {labels}")


def test_heal_repoints_legacy_single_source() -> None:
    pipe = TransformPipeline(steps=[
        TransformStep(id="s1", kind="filter", inputs=["source:raw"], filterExpr="1=1"),
    ])
    assert heal_pipeline_inputs(pipe, {"sales"}) is True
    assert pipe.steps[0].inputs == ["source:sales"], pipe.steps[0].inputs

    # Ambiguous (two tables) or already-valid pipelines are left alone.
    two = TransformPipeline(steps=[
        TransformStep(id="s1", kind="filter", inputs=["source:raw"], filterExpr="1=1"),
    ])
    assert heal_pipeline_inputs(two, {"sales", "spend"}) is False
    assert two.steps[0].inputs == ["source:raw"]
    live = TransformPipeline(steps=[
        TransformStep(id="s1", kind="filter", inputs=["source:raw"], filterExpr="1=1"),
    ])
    assert heal_pipeline_inputs(live, {"raw"}) is False
    print("[heal] source:raw re-pointed only when unambiguous")


def main() -> int:
    root = get_settings().data_path / "projects" / PROJECT_ID
    shutil.rmtree(root, ignore_errors=True)
    try:
        test_names_are_stable_as_sources_are_added()
        test_multi_sheet_is_namespaced_by_file()
        test_non_ascii_names_are_distinct_and_stable()
        test_unreadable_files_are_reported_not_swallowed()
        test_source_labels_name_the_sheet_only_when_needed()
        test_heal_repoints_legacy_single_source()
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
