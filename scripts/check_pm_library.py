"""Check the imported real PM library against direct dataframe calculations."""

import json
import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.table_queries import TableQuery, query_tables
from backend.tables import experiment_from_name, read_table


def main():
    tables = []
    for path in (ROOT / "data" / "assets").glob("*/metadata.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item["role"] == "pm" and experiment_from_name(item["name"]):
            tables.append({**item, "path": path.parent / ("original" + item["extension"])})
    assert len(tables) == 27, f"Expected the 27 supplied PM flight files; found {len(tables)}."
    frames = []
    for item in tables:
        assert hashlib.sha256(item["path"].read_bytes()).hexdigest() == item["sha256"]
        assert hashlib.sha256(Path(item["imported_from"]).read_bytes()).hexdigest() == item["sha256"]
        frame = read_table(item["path"])
        assert item["info"]["invalid_timestamps"] == 0
        assert item["info"]["preamble_lines_skipped"] == 2
        for key, value in experiment_from_name(item["name"]).items():
            frame[key] = value
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    assert len(combined) == 5757
    pm = next(c for c in combined if c.startswith("PM2.5"))
    result = query_tables(tables, TableQuery(columns=[pm], group_by="altitude_setting_m"))
    expected = combined.groupby("altitude_setting_m")[pm].mean()
    for group in result["result"]:
        assert abs(group["statistics"][pm]["mean"] - expected[int(group["group"])]) < 1e-9
    peak = query_tables(tables, TableQuery(operation="rows", columns=["timeStamp", pm],
                                         sort_by=pm, limit=1))
    assert peak["result"][0][pm] == combined[pm].max()
    print(json.dumps({"files": len(tables), "rows": len(combined), "schemas": len({tuple(t["info"]["columns"]) for t in tables}),
                      "timestamp_parsing": "all valid", "checks": ["preamble/BOM parsing", "grouped PM mean", "peak row"]}))


if __name__ == "__main__":
    main()
