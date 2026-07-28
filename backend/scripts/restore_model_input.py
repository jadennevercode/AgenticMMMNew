"""Rebuild every model-input_2.32 restore artifact. Idempotent.

Run from backend/:
    PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input
"""
from __future__ import annotations

import sys

from scripts.restore import (curated, factor_tree, paths, profile, raw_export,
                             readme, source, taxonomy)


def main() -> int:
    paths.mkdirs()
    print(f"source : {paths.source_workbook()}")
    print(f"output : {paths.OUT}")

    station = source.load_station()
    granularity = source.load_granularity()
    print(f"loaded : {len(station)} ledger rows, "
          f"{granularity['indicator'].nunique()} planned indicators")

    tmap = taxonomy.derive(station)
    print(f"taxonomy: {tmap.l1}")

    tree = factor_tree.build(station, granularity)
    factor_tree.write(tree)
    origin = tree["origin"].value_counts().to_dict()
    print(f"tree   : {len(tree)} rows {origin}")

    raw_files = raw_export.write(station)
    print(f"raw    : {len(raw_files)} workbooks")

    long = curated.build(station, tmap)
    curated.write(long, station, tmap)
    print(f"curated: {len(long)} rows x {len(long.columns)} cols")

    profile.write(long)
    readme.write({
        "treeRows": len(tree), "originCounts": origin,
        "rawFiles": len(raw_files), "curatedRows": len(long),
        "taxonomy": tmap,
    })
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
