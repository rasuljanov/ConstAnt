"""Import the supplied local flight CSVs without changing the research originals."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.tables import experiment_from_name, summarize_table


def import_files(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir():
        raise ValueError("Source directory does not exist.")
    destination.mkdir(parents=True, exist_ok=True)
    imported, existing, rows, schemas = [], [], 0, set()
    for path in sorted(source.glob("*")):
        if path.suffix.lower() != ".csv" or not experiment_from_name(path.name):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        identifier = uuid5(NAMESPACE_URL, str(path) + digest).hex
        folder = destination / identifier
        info = summarize_table(path)
        info["experiment"] = experiment_from_name(path.name)
        rows += info["rows"]
        schemas.add(tuple(info["columns"]))
        if (folder / "metadata.json").exists():
            existing.append(identifier)
            continue
        folder.mkdir(exist_ok=True)
        shutil.copyfile(path, folder / "original.csv")
        item = {"id": identifier, "name": path.name, "kind": "table", "role": "pm",
                "extension": ".csv", "bytes": path.stat().st_size, "sha256": digest,
                "created_at": datetime.now(timezone.utc).isoformat(), "info": info,
                "imported_from": str(path)}
        temporary = folder / "metadata.tmp"
        temporary.write_text(json.dumps(item, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(folder / "metadata.json")
        imported.append(identifier)
    return {"imported": len(imported), "already_present": len(existing), "rows": rows,
            "schemas": len(schemas), "source": str(source)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT / "data" / "assets")
    args = parser.parse_args()
    print(json.dumps(import_files(args.source, args.destination), ensure_ascii=True))
