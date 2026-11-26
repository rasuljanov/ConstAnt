"""Archive existing unchanged-Instruct chat results without running a model."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from backend.inference import MODEL_ID
from backend.visual_analysis import visual_count_table, visual_summary
from notes.generate_report import markdown_table, save_figure


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError(f"Invalid stored record ID: {value!r}")
    return value


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def asset_ids(run):
    return list(dict.fromkeys([*run.get("effective_asset_ids", run["request"].get("asset_ids", [])),
                               *run["request"].get("asset_ids", []), *run.get("context_missing", []),
                               *(item["id"] for item in run.get("evidence", []))]))


def call_records(run):
    calls = []
    attempts = run.get("planner_attempts")
    if attempts:
        calls.extend(("planner", a.get("metrics", {}), []) for a in attempts)
    elif run.get("planner_metrics"):
        calls.append(("planner", run["planner_metrics"], []))
    for batch in run.get("visual_result", {}).get("batches", []):
        calls.extend(("visual", a.get("metrics", {}), batch["unit_ids"]) for a in batch["attempts"])
    if run.get("metrics"):
        calls.append(("answer", run["metrics"], []))
    return [{"run_id": run["id"], "call_index": i, "stage": stage, "unit_ids": units, **metrics}
            for i, (stage, metrics, units) in enumerate(calls, 1)]


def summarize(run, sources):
    model = run.get("model", {})
    backend = model.get("backend")
    inferred = not bool(backend)
    if not backend:
        backend = "transformers" if model.get("quantization") in ("NF4 4-bit", "FP16") else "unrecorded"
    calls = call_records(run)
    units = [u for s in run.get("visual_result", {}).get("sources", []) for u in s.get("units", [])]
    kinds = sorted({sources[i].get("kind", "missing") for i in asset_ids(run)})
    counts = Counter(u.get("status", "unprocessed") for u in units)
    row = {"run_id": run["id"], "chat_id": run["request"].get("chat_id"), "created_at": run.get("created_at"),
           "question": run["request"].get("question", ""), "status": run.get("status"),
           "source_kinds": "+".join(kinds) or "text", "backend": backend, "backend_inferred": inferred,
           "quantization_recorded": model.get("quantization"), "revision_recorded": model.get("revision"),
           "wall_seconds": number(run.get("wall_seconds")), "model_calls_recorded": number(run.get("model_calls")),
           "saved_call_records": len(calls), "reused_visual_run_id": run.get("reused_visual_run_id"),
           "target_views": number(run.get("visual_result", {}).get("total")),
           "observed_views": counts["observed"] if units else None,
           "blank_views": counts["blank"] if units else None, "failed_views": counts["failed"] if units else None,
           "unprocessed_views": counts["unprocessed"] if units else None,
           "final_truncated": run.get("metrics", {}).get("truncated"),
           "sources_verified": all(sources[i]["state"] == "verified" for i in asset_ids(run)),
           "replay_ready": False}
    complete_calls = bool(calls) and len(calls) == row["model_calls_recorded"]
    row["call_metrics_complete"] = complete_calls
    for field in ("input_tokens", "output_tokens"):
        values = [number(c.get(field)) for c in calls]
        row["total_" + field] = sum(values) if complete_calls and all(v is not None for v in values) else None
    row["replay_ready"] = row["sources_verified"] and bool(run.get("system_prompt")) and run.get("status") == "completed"
    return row


def freeze_source(data, objects, identifier):
    safe_id(identifier)
    folder = data / "assets" / identifier
    if not folder.resolve().is_relative_to((data / "assets").resolve()):
        raise ValueError(f"Source is outside upload storage: {identifier}")
    metadata = folder / "metadata.json"
    if not metadata.is_file():
        return {"id": identifier, "state": "missing", "reason": "Asset metadata was already unavailable."}
    item = json.loads(metadata.read_bytes())
    if item.get("id") != identifier or not re.fullmatch(r"[a-f0-9]{64}", item.get("sha256", "")):
        raise ValueError(f"Invalid source identity/hash: {identifier}")
    extension = item.get("extension", "")
    if not re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", extension):
        raise ValueError(f"Invalid source extension: {identifier}")
    original = folder / ("original" + extension)
    if not original.resolve().is_relative_to((data / "assets").resolve()):
        raise ValueError(f"Source is outside upload storage: {identifier}")
    result = {"id": identifier, "name": item["name"], "kind": item["kind"], "sha256": item["sha256"], "metadata": item}
    if not original.is_file():
        return result | {"state": "missing", "reason": "Original file was already unavailable."}
    destination = objects / item["sha256"] / ("original" + extension.lower())
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if digest(destination) != item["sha256"]:
            raise ValueError(f"An existing archived object is corrupt: {destination}")
    else:
        temporary = destination.with_name("copy-" + uuid4().hex + ".tmp")
        try:
            shutil.copyfile(original, temporary)
            actual = digest(temporary)
            if actual != item["sha256"]:
                return result | {"state": "hash_mismatch", "actual_sha256": actual}
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return result | {"state": "verified", "object_file": destination}


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows)


def charts(snapshot, rows, count_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    directory = snapshot / "charts"
    directory.mkdir()
    labels = [r["run_id"][:8] + " · " + r["source_kinds"] + (" · reused" if r["reused_visual_run_id"] else "") for r in rows]
    colors = ["#4d8066" if r["backend"] == "vllm" else "#6885ab" for r in rows]
    created = []
    fig, ax = plt.subplots(figsize=(12, max(4, len(rows) * .38 + 2)))
    measured = [(i, r["wall_seconds"]) for i, r in enumerate(rows) if r["wall_seconds"] is not None and r["wall_seconds"] > 0]
    ax.barh([i for i, _ in measured], [v for _, v in measured], color=[colors[i] for i, _ in measured])
    ax.set_yticks(range(len(rows)), labels, fontsize=8)
    ax.invert_yaxis()
    if measured:
        ax.set_xscale("log")
    ax.set(xlabel="Recorded job wall time, seconds (log scale)", title="Unchanged Instruct baseline · historical request times")
    for i, value in measured:
        ax.text(value * 1.06, i, f"{value:,.2f}s", va="center", fontsize=8)
    ax.margins(x=.2)
    ax.grid(axis="x", alpha=.18)
    fig.text(.02, .01, "Green: vLLM. Blue: Transformers. Precision is in run-metrics.csv. Work and cache states differ; no speed comparison.", fontsize=8)
    fig.tight_layout(rect=(0, .035, 1, 1))
    created.append(save_figure(fig, directory, "request-times", plt))

    fig, axes = plt.subplots(1, 2, figsize=(13, max(4, len(rows) * .38 + 2)))
    for ax, field, title in zip(axes, ("model_calls_recorded", "total_output_tokens"), ("Model calls, including retries", "Output tokens across saved calls")):
        points = [(i, r[field]) for i, r in enumerate(rows) if r[field] is not None]
        ax.barh([i for i, _ in points], [v for _, v in points], color=[colors[i] for i, _ in points])
        ax.set_yticks(range(len(rows)), labels if ax is axes[0] else [], fontsize=8)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11)
        ax.grid(axis="x", alpha=.18)
    fig.suptitle("Historical workload · missing token totals are omitted")
    fig.tight_layout()
    created.append(save_figure(fig, directory, "model-work", plt))

    scanned = [r for r in rows if r["target_views"] is not None]
    if scanned:
        fig, ax = plt.subplots(figsize=(12, max(4, len(scanned) * .5 + 2)))
        left = [0] * len(scanned)
        for field, label, color in (("observed_views", "Observed", "#4d8066"), ("blank_views", "Blank/no-data display", "#bdc5c0"),
                                    ("failed_views", "Failed", "#c5725b"), ("unprocessed_views", "Unprocessed", "#dfb367")):
            values = [100 * (r[field] or 0) / max(r["target_views"], 1) for r in scanned]
            ax.barh(range(len(scanned)), values, left=left, label=label, color=color)
            left = [a + b for a, b in zip(left, values)]
        ax.set_yticks(range(len(scanned)), [f"{r['run_id'][:8]} · {int(r['target_views'])} views" + (" · reused" if r["reused_visual_run_id"] else "") for r in scanned], fontsize=8)
        ax.invert_yaxis()
        ax.set(xlim=(0, 100), xlabel="Share of scheduled views (%)", title="Visual coverage · blank/failed views do not establish zero objects")
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.13), ncol=2, frameon=False, fontsize=9)
        fig.tight_layout()
        created.append(save_figure(fig, directory, "visual-coverage", plt))

    for kind in ("raster", "video"):
        points = [r for r in count_rows if r["kind"] == kind and not r["reused_visual_run_id"]]
        if not points:
            continue
        fig, ax = plt.subplots(figsize=(12, max(4, len(points) * .3 + 2)))
        for i, row in enumerate(points):
            if kind == "video":
                ax.plot([row["min_per_frame"], row["max_per_frame"]], [i, i], color="#6885ab", linewidth=3)
                ax.scatter([row["min_per_frame"], row["max_per_frame"]], [i, i], color="#6885ab", s=22)
            else:
                ax.barh(i, row["estimated_visible_count"], color="#4d8066")
            value = f"{row['min_per_frame']}–{row['max_per_frame']}" if kind == "video" else str(row["estimated_visible_count"])
            end = row["max_per_frame"] if kind == "video" else row["estimated_visible_count"]
            ax.annotate(value, (end, i), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8)
        ax.set_yticks(range(len(points)), [r["run_id"][:8] + " · " + r["class_name"].replace("_", " ") for r in points], fontsize=8)
        ax.invert_yaxis()
        ax.set(xlabel="Min–max per sampled frame; not unique vehicles" if kind == "video" else "Estimated visible count in numeric observations only",
               title="Baseline model predictions · " + kind + " · unreviewed; failed views make totals partial")
        ax.set_xlim(left=0)
        ax.margins(x=.2)
        ax.grid(axis="x", alpha=.18)
        fig.tight_layout()
        created.append(save_figure(fig, directory, "predictions-" + kind, plt))
    return created


def snapshot_baseline(data_dir, notes_dir, snapshot_id=None):
    data, notes = Path(data_dir).resolve(), Path(notes_dir).resolve()
    selection_started_at = datetime.now(timezone.utc).isoformat()
    snapshot_id = snapshot_id or "baseline-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", snapshot_id):
        raise ValueError("Snapshot ID must contain only letters, numbers, underscores and hyphens.")
    records = []
    for path in sorted((data / "runs").glob("*.json")):
        raw = path.read_bytes()
        run = json.loads(raw)
        if safe_id(run["id"]) != path.stem:
            raise ValueError("Stored run ID does not match its filename.")
        model = run.get("model", {})
        if (model.get("model_id", MODEL_ID) != MODEL_ID or model.get("model_variant") not in (None, "baseline")
                or any(model.get(k) for k in ("adapter_id", "adapter_path", "lora_adapter", "lora_modules"))):
            raise ValueError(f"Run {run['id']} is not an unchanged-Instruct baseline.")
        records.append((run, raw))
    analyses = sorted([r for r, _ in records if r["request"]["action"] == "analyze"], key=lambda r: (r.get("created_at", ""), r["id"]))
    if not analyses:
        raise ValueError("No saved analysis runs found; no snapshot created.")
    snapshot = notes / "baselines" / snapshot_id
    snapshot.mkdir(parents=True, exist_ok=False)
    for name in ("runs", "chats", "chat-metadata", "context"):
        (snapshot / name).mkdir()
    print(f"Freezing {len(analyses)} analyses and {len(records) - len(analyses)} control records into {snapshot}", flush=True)
    try:
        raw_manifest = []
        for run, raw in records:
            target = snapshot / "runs" / (run["id"] + ".json")
            target.write_bytes(raw)
            raw_manifest.append({"id": run["id"], "action": run["request"]["action"], "file": target.relative_to(snapshot).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()})
        sources, pending = {}, {safe_id(i) for r in analyses for i in asset_ids(r)}
        while pending:
            identifier = pending.pop()
            source = freeze_source(data, data / "experiments" / "baseline-objects", identifier)
            if "object_file" in source:
                source["object_file"] = Path(os.path.relpath(source["object_file"], snapshot)).as_posix()
            sources[identifier] = source
            parent = source.get("metadata", {}).get("info", {}).get("parent_id")
            if parent and parent not in sources:
                pending.add(safe_id(parent))
            print(f"Source {identifier[:8]}: {source['state']}", flush=True)
        for run in analyses:
            for evidence in run.get("evidence", []):
                if evidence.get("sha256") and evidence["sha256"] != sources[evidence["id"]].get("sha256"):
                    raise ValueError(f"Source {evidence['id']} no longer matches the hash recorded in run {run['id']}.")
        metadata = {}
        for path in (data / "chats").glob("*.json"):
            safe_id(path.stem)
            raw = path.read_bytes()
            metadata[path.stem] = json.loads(raw)
            (snapshot / "chat-metadata" / path.name).write_bytes(raw)
        for relative in ("backend/main.py", "backend/inference.py", "backend/vllm_engine.py", "backend/media.py", "backend/tables.py",
                         "backend/table_queries.py", "backend/visual_analysis.py", "backend/requirements.txt", "backend/requirements-inference.txt",
                         "backend/requirements-vllm.txt", "scripts/serve_vllm.py", "notes/snapshot_baseline.py", "notes/reports/vllm-environment.txt"):
            original = PROJECT / relative
            if original.is_file():
                target = snapshot / "context" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
        launch = data / "server" / "vllm-launch.json"
        if launch.is_file():
            shutil.copyfile(launch, snapshot / "context" / "vllm-launch.json")
        rows = [summarize(r, sources) for r in analyses]
        write_csv(snapshot / "run-metrics.csv", rows, list(rows[0]))
        calls = [c for r in analyses for c in call_records(r)]
        write_csv(snapshot / "call-metrics.csv", calls, ["run_id", "call_index", "stage", "unit_ids", "backend", "input_tokens", "output_tokens",
                  "generation_seconds", "request_seconds", "inference_seconds", "output_tokens_per_second", "request_output_tokens_per_second", "peak_allocated_vram_gb", "truncated"])
        count_rows = []
        for run in analyses:
            for source in visual_summary(run["visual_result"]) if run.get("visual_result") else []:
                for label, values in source["counts"].items():
                    count_rows.append({"run_id": run["id"], "source_id": source["id"], "source_name": source["name"], "kind": source["kind"],
                                       "class_name": label, "estimated_visible_count": values.get("estimated_visible_count"),
                                       "min_per_frame": values.get("min_per_sampled_frame"), "max_per_frame": values.get("max_per_sampled_frame"),
                                       "views_with_numeric_count": values["views_with_numeric_count"], "failed_views": source["failed_views"],
                                       "unreported_or_uncertain_views": values["unreported_or_uncertain_views"], "reused_visual_run_id": run.get("reused_visual_run_id")})
        write_csv(snapshot / "predicted-counts.csv", count_rows, ["run_id", "source_id", "source_name", "kind", "class_name", "estimated_visible_count",
                  "min_per_frame", "max_per_frame", "views_with_numeric_count", "failed_views", "unreported_or_uncertain_views", "reused_visual_run_id"])
        cases = []
        by_chat = defaultdict(list)
        for run, row in zip(analyses, rows):
            chat = safe_id(run["request"]["chat_id"]) if run["request"].get("chat_id") else "ungrouped"
            by_chat[chat].append(run)
            if run.get("status") == "completed" and run.get("answer"):
                cases.append({"case_id": run["id"], "model_variant": "baseline", "adapter_id": None, "question": run["request"]["question"],
                              "request": run["request"], "effective_asset_ids": run.get("effective_asset_ids", run["request"].get("asset_ids", [])),
                              "source_ids": asset_ids(run), "run_file": "runs/" + run["id"] + ".json", "run_sha256": digest(snapshot / "runs" / (run["id"] + ".json")),
                              "sources_verified": row["sources_verified"], "replay_ready": row["replay_ready"], "quality_reviewed": False,
                              "response_is_ground_truth": False, "reused_visual_run_id": run.get("reused_visual_run_id"),
                              "context_policy": "Saved baseline history/tool results/observations are frozen; autonomous chat rollout is a separate comparison."})
        with (snapshot / "cases.jsonl").open("w", encoding="utf-8") as stream:
            for case in cases:
                stream.write(json.dumps(case, ensure_ascii=False, allow_nan=False) + "\n")
        chat_links = []
        for chat, members in by_chat.items():
            title = metadata.get(chat, {}).get("title") or members[0]["request"]["question"][:100]
            chat_links.append("- [" + title.replace("\n", " ").replace("[", "\\[").replace("]", "\\]") + "](chats/" + chat + ".md)")
            lines = ["# " + title.replace("\n", " "), "", "Unchanged Instruct baseline outputs; unreviewed model predictions, not reference answers.", ""]
            for run in members:
                lines += ["## Run " + run["id"], "", "**Question:** " + run["request"]["question"], "", "**Saved answer:**", "", run.get("answer") or "No completed answer.", "",
                          "[Full raw record, prompts, history, calculations and observations](../runs/" + run["id"] + ".json)", ""]
                for identifier in asset_ids(run):
                    source = sources[identifier]
                    if source.get("object_file"):
                        relative = Path(os.path.relpath(snapshot / source["object_file"], snapshot / "chats")).as_posix()
                        lines += ["Source: [" + source["name"].replace("[", "\\[").replace("]", "\\]") + "](" + relative + ")", ""]
                if run.get("visual_result") and "**Model-estimated counts" not in (run.get("answer") or ""):
                    lines += [visual_count_table(run["visual_result"]), ""]
            (snapshot / "chats" / (chat + ".md")).write_text("\n".join(lines), encoding="utf-8")
        figures = charts(snapshot, rows, count_rows)
        manifest = {"snapshot_id": snapshot_id, "selection_started_at_utc": selection_started_at, "captured_at_utc": datetime.now(timezone.utc).isoformat(), "model_id": MODEL_ID,
                    "model_variant": "baseline", "designation": "User confirmed these are unchanged Instruct results; raw metadata is preserved.",
                    "status": "complete", "analysis_count": len(analyses), "completed_cases": len(cases), "chat_count": len(by_chat),
                    "control_record_count": len(records) - len(analyses), "records": raw_manifest, "sources": list(sources.values()),
                    "quality_scores": None, "context_code_policy": "context/ contains code and environment at archive time, not attested historical code for each run."}
        write_json(snapshot / "manifest.json", manifest)
        summary = ["# Unchanged Qwen3-VL-4B-Instruct baseline", "", "Snapshot: `" + snapshot_id + "` · " + manifest["captured_at_utc"], "",
                   f"Saved **{len(analyses)} analyses across {len(by_chat)} chats**, plus {manifest['control_record_count']} load/unload/control records for audit. "
                   f"**{sum(s['state'] == 'verified' for s in sources.values())} of {len(sources)} referenced/parent sources** were verified and copied into deduplicated storage under `data/experiments/baseline-objects`.", "",
                   "This is the original Instruct baseline, not a separately pretrained Base model. No QLoRA training or inference was performed by this export.", "",
                   "## Saved conversations", "", *chat_links, "",
                   "## Results and measurements", "", markdown_table(rows, ["run_id", "source_kinds", "backend", "quantization_recorded", "status", "wall_seconds", "model_calls_recorded"]), "",
                   "Each run's original answer, request, history, system prompt, planner attempts, computed table results and visual observations remain in `runs/<id>.json`. "
                   "Human-readable conversations are in `chats/`. Stable comparison case IDs and source references are in `cases.jsonl`. "
                   "CSV exports: `run-metrics.csv`, `call-metrics.csv`, and `predicted-counts.csv`.", "", "## Visual coverage", "",
                   markdown_table([r for r in rows if r["target_views"] is not None], ["run_id", "target_views", "observed_views", "blank_views", "failed_views", "reused_visual_run_id"]), "",
                   "Failed/uncertain views make count totals incomplete. Blank/no-data display tiles are not evidence that no equipment exists. "
                   "Video counts are min–max per sampled frame and must not be added into unique vehicles. Charts show model predictions, not checked labels.", "", "## Charts", ""]
        for figure in figures:
            summary += ["![" + figure.removesuffix(".png").replace("-", " ") + "](charts/" + figure + ")", ""]
        summary += ["## Comparison limits", "", "- These are historical, exploratory requests with different inputs, prompts, processing budgets and cache states. The timing charts do not establish a controlled engine/model speedup.",
                    "- Keep Transformers/NF4 and vLLM/server-managed records distinct. Legacy backend names are inferred only where the saved precision identifies Transformers. vLLM revision/precision fields were not attested by its API; the copied launcher is archive-time context.",
                    "- No accuracy, count error, or groundedness score is invented. Existing model answers are not training targets or ground truth. Independently reviewed references are still needed.",
                    "- Follow-up requests may reuse earlier baseline visual observations and history. Match that evidence exactly for a model-only comparison; rerunning the full pipeline or using adapter-generated history is a separate condition.",
                    "- Source originals are hash-verified backups, but exact historical processed tensors/cache state/software versions were not saved for every run. Freeze a common replay protocol before a controlled QLoRA comparison.",
                    "- Copy both this snapshot and its referenced `data/experiments/baseline-objects` when moving the experiment. Deleting a live chat/resource does not delete these backups.",
                    "- This snapshot is never overwritten. New chats require another snapshot. `checksums.sha256` covers all snapshot files; source hashes/paths are in `manifest.json`.", ""]
        (snapshot / "report.md").write_text("\n".join(summary), encoding="utf-8")
        files = sorted(p for p in snapshot.rglob("*") if p.is_file())
        (snapshot / "checksums.sha256").write_text("".join(digest(p) + "  " + p.relative_to(snapshot).as_posix() + "\n" for p in files), encoding="utf-8")
        return snapshot
    except Exception as exc:
        write_json(snapshot / "EXPORT_FAILED.json", {"status": "incomplete", "error": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("CONST_VLM_DATA", PROJECT / "data")))
    parser.add_argument("--notes-dir", type=Path, default=PROJECT / "notes")
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    try:
        print(snapshot_baseline(args.data_dir, args.notes_dir, args.snapshot_id))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f"Baseline snapshot not completed: {exc}\n")
