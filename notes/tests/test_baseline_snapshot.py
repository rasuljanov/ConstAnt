"""Archive tests use fake records/bytes only in temporary folders; no model runs."""

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from notes.snapshot_baseline import digest, freeze_source, snapshot_baseline, summarize


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def source(data, identifier="d" * 32):
    folder = data / "assets" / identifier
    folder.mkdir(parents=True)
    payload = b"TEST STUB: source bytes, not an actual video."
    (folder / "original.mp4").write_bytes(payload)
    item = {"id": identifier, "name": "TEST.mp4", "extension": ".mp4", "kind": "video",
            "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "info": {}}
    write(folder / "metadata.json", item)
    return item


def run(item):
    identifier = item["id"]
    metrics = {"input_tokens": 10, "output_tokens": 2, "generation_seconds": 1, "truncated": False}
    return {"id": "a" * 32, "created_at": "2026-11-18T00:00:00+00:00", "status": "completed", "wall_seconds": 6,
            "request": {"action": "analyze", "question": "TEST QUESTION", "asset_ids": [identifier], "chat_id": "c" * 32, "history": []},
            "model": {"model_id": "Qwen/Qwen3-VL-4B-Instruct", "quantization": "NF4 4-bit", "revision": "TEST REVISION"},
            "system_prompt": "TEST SYSTEM", "answer": "TEST BASELINE ANSWER", "model_calls": 4, "metrics": metrics,
            "planner_metrics": {"input_tokens": 999, "output_tokens": 999},
            "planner_attempts": [{"metrics": metrics}, {"metrics": metrics, "validation_error": "TEST RETRY"}],
            "evidence": [{"id": identifier, "kind": "video", "sha256": item["sha256"]}],
            "visual_result": {"total": 2, "completed": 2, "sources": [
                {"id": identifier, "name": item["name"], "kind": "video", "unit_count": 2, "units": [
                    {"unit_id": "one", "status": "observed", "counts": {"truck": 2}},
                    {"unit_id": "two", "status": "failed", "counts": {}}]}],
                "batches": [{"unit_ids": ["one", "two"], "attempts": [{"metrics": metrics}]}]}}


def test_snapshot_keeps_raw_outputs_sources_context_and_honest_metrics(tmp_path):
    data, notes = tmp_path / "data", tmp_path / "notes"
    item = source(data)
    base = run(item)
    write(data / "runs" / (base["id"] + ".json"), base)
    reused = copy.deepcopy(base)
    reused.update(id="b" * 32, created_at="2026-11-18T01:00:00+00:00", reused_visual_run_id=base["id"], model_calls=1)
    reused["model"] = {"backend": "vllm", "quantization": "server-managed", "revision": None}
    reused.pop("planner_attempts")
    reused.pop("planner_metrics")
    reused["visual_result"].pop("batches")
    write(data / "runs" / (reused["id"] + ".json"), reused)
    control = {"id": "e" * 32, "status": "completed", "request": {"action": "load"}}
    write(data / "runs" / (control["id"] + ".json"), control)
    write(data / "chats" / ("c" * 32 + ".json"), {"title": "TEST CHAT", "pinned": True})
    originals = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
    snapshot = snapshot_baseline(data, notes, "test-baseline")
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    assert (snapshot / "runs" / (base["id"] + ".json")).read_bytes() == originals[data / "runs" / (base["id"] + ".json")]
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["analysis_count"] == manifest["completed_cases"] == 2
    assert manifest["control_record_count"] == 1 and manifest["quality_scores"] is None
    frozen = (snapshot / manifest["sources"][0]["object_file"]).resolve()
    assert digest(frozen) == item["sha256"]
    cases = [json.loads(line) for line in (snapshot / "cases.jsonl").read_text().splitlines()]
    assert all(c["replay_ready"] and not c["quality_reviewed"] and not c["response_is_ground_truth"] for c in cases)
    with (snapshot / "run-metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["total_input_tokens"] == "40" and rows[0]["total_output_tokens"] == "8"
    assert rows[0]["failed_views"] == "1" and rows[0]["backend"] == "transformers"
    assert rows[1]["saved_call_records"] == "1" and rows[1]["revision_recorded"] == ""
    assert rows[1]["total_output_tokens"] == "2"
    with (snapshot / "predicted-counts.csv").open(encoding="utf-8-sig", newline="") as stream:
        counts = list(csv.DictReader(stream))
    assert counts[0]["estimated_visible_count"] == "" and counts[0]["min_per_frame"] == counts[0]["max_per_frame"] == "2"
    report = (snapshot / "report.md").read_text(encoding="utf-8")
    assert "TEST CHAT" in report and "No accuracy" in report and "QLoRA training" in report
    assert "TEST BASELINE ANSWER" in next((snapshot / "chats").glob("*.md")).read_text()
    assert len(list((snapshot / "charts").glob("*.png"))) == 4
    for line in (snapshot / "checksums.sha256").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        assert digest(snapshot / relative) == expected
    with pytest.raises(FileExistsError):
        snapshot_baseline(data, notes, "test-baseline")
    (data / "assets" / item["id"] / "original.mp4").unlink()
    assert frozen.is_file() and digest(frozen) == item["sha256"]


def test_duplicate_source_hashes_reuse_backup_and_corrupt_backups_are_not_overwritten(tmp_path):
    data, objects = tmp_path / "data", tmp_path / "objects"
    first, second = source(data), source(data, "f" * 32)
    a = freeze_source(data, objects, first["id"])
    b = freeze_source(data, objects, second["id"])
    assert a["object_file"] == b["object_file"] and len(list(objects.glob("*/original.*"))) == 1
    a["object_file"].write_bytes(b"TEST CORRUPTION")
    with pytest.raises(ValueError, match="corrupt"):
        freeze_source(data, objects, first["id"])
    assert a["object_file"].read_bytes() == b"TEST CORRUPTION"


def test_changed_and_missing_sources_are_not_claimed_verified(tmp_path):
    data, objects = tmp_path / "data", tmp_path / "objects"
    item = source(data)
    (data / "assets" / item["id"] / "original.mp4").write_bytes(b"TEST CHANGED")
    result = freeze_source(data, objects, item["id"])
    assert result["state"] == "hash_mismatch" and not list(objects.glob("*/original.*"))
    assert not list(objects.glob("*/*.tmp"))
    missing = freeze_source(data, objects, "9" * 32)
    assert missing["state"] == "missing"
    row = summarize(run(item), {item["id"]: result})
    assert not row["sources_verified"] and not row["replay_ready"]


def test_missing_call_measurements_remain_missing(tmp_path):
    item = source(tmp_path)
    saved = run(item)
    saved["model_calls"] = 5
    result = summarize(saved, {item["id"]: item | {"state": "verified"}})
    assert result["total_output_tokens"] is None and not result["call_metrics_complete"]


@pytest.mark.parametrize("model", [{"adapter_id": "TEST-QLORA"}, {"model_variant": "qlora"}, {"model_id": "different-model"}])
def test_adapter_and_other_model_runs_cannot_be_labeled_baseline(tmp_path, model):
    data, notes = tmp_path / "data", tmp_path / "notes"
    saved = run(source(data))
    saved["model"].update(model)
    write(data / "runs" / (saved["id"] + ".json"), saved)
    with pytest.raises(ValueError, match="not an unchanged"):
        snapshot_baseline(data, notes, "test-baseline")
    assert not (notes / "baselines").exists()


@pytest.mark.parametrize("extension", ["/../../secret", ".mp4/../../secret", "\\secret"])
def test_source_metadata_cannot_escape_upload_storage(tmp_path, extension):
    item = source(tmp_path)
    item["extension"] = extension
    write(tmp_path / "assets" / item["id"] / "metadata.json", item)
    with pytest.raises(ValueError, match="extension"):
        freeze_source(tmp_path, tmp_path / "objects", item["id"])


def test_snapshot_name_cannot_escape_notes(tmp_path):
    with pytest.raises(ValueError, match="Snapshot ID"):
        snapshot_baseline(tmp_path / "data", tmp_path / "notes", "../outside")
