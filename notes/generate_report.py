"""Render measured experiment logs; never run training or invent result rows."""

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMAS = {
    "retrieval": "run_id,cohort_id,index,index_parameters,seed,n_vectors,n_queries,k,ann_recall_at_k,relevance_recall_at_k,search_p50_ms,search_p95_ms,build_seconds,peak_rss_mib,index_size_mib,status,details_file".split(","),
    "models": "run_id,cohort_id,task,model_variant,adapter_id,retrieval_run_id,seed,n_examples,n_claims_reviewed,qa_accuracy,count_mae,grounded_claim_rate,latency_p50_s,latency_p95_s,peak_vram_gib,output_tokens_per_s,status,details_file".split(","),
    "training_steps": "run_id,adapter_id,step,train_loss,eval_loss".split(","),
}
NUMBERS = {
    "retrieval": SCHEMAS["retrieval"][4:15],
    "models": SCHEMAS["models"][6:16],
    "training_steps": ["step", "train_loss", "eval_loss"],
}
RATES = {"ann_recall_at_k", "relevance_recall_at_k", "qa_accuracy", "grounded_claim_rate"}
COUNTS = {"seed", "n_vectors", "n_queries", "k", "n_examples", "n_claims_reviewed", "step"}


def read_results(directory, kind):
    path = directory / (kind + ".csv")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != SCHEMAS[kind]:
            raise ValueError(f"{path}: headers must match the documented {kind} schema.")
        rows = []
        seen = set()
        for line, raw in enumerate(reader, 2):
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError(f"{path}:{line}: malformed CSV row; check quoting and column count.")
            row = {k: v.strip() for k, v in raw.items()}
            if not any(row.values()):
                continue
            for key in ("run_id", "cohort_id", "task", "adapter_id", "retrieval_run_id"):
                if key in row and (row[key] or key not in ("adapter_id",)):
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", row[key]):
                        raise ValueError(f"{path}:{line}: {key} must be a nonempty safe ID.")
            for key in NUMBERS[kind]:
                value = None if row[key] == "" else float(row[key])
                if value is not None and (not math.isfinite(value) or value < 0 or (key in RATES and value > 1)
                                          or (key in COUNTS and not value.is_integer())):
                    raise ValueError(f"{path}:{line}: invalid value for {key}.")
                row[key] = int(value) if value is not None and key in COUNTS else value
            identity = (row["run_id"], row.get("step"))
            if identity in seen:
                raise ValueError(f"{path}:{line}: duplicate run/step ID.")
            seen.add(identity)
            if kind == "training_steps":
                if row["step"] is None or not row["adapter_id"] or all(row[k] is None for k in ("train_loss", "eval_loss")):
                    raise ValueError(f"{path}:{line}: training rows need adapter, step and at least one loss.")
            else:
                if row["status"] not in ("planned", "completed", "failed", "skipped"):
                    raise ValueError(f"{path}:{line}: invalid status.")
                details = row["details_file"].replace("\\", "/")
                if details and not re.fullmatch(r"reports/[A-Za-z0-9_-]+\.md", details):
                    raise ValueError(f"{path}:{line}: details_file must be a relative reports/<id>.md path.")
                if kind == "retrieval":
                    if not row["index"] or not isinstance(json.loads(row["index_parameters"] or "{}"), dict):
                        raise ValueError(f"{path}:{line}: index and JSON index_parameters object are required.")
                    required = ("n_vectors", "n_queries", "k", "ann_recall_at_k", "search_p95_ms")
                else:
                    if row["model_variant"] not in ("baseline", "qlora"):
                        raise ValueError(f"{path}:{line}: model_variant must be baseline or qlora.")
                    if (row["model_variant"] == "qlora") != bool(row["adapter_id"]):
                        raise ValueError(f"{path}:{line}: only QLoRA rows must identify an adapter.")
                    required = ("n_examples", "latency_p95_s", "peak_vram_gib")
                if row["status"] == "completed":
                    if any(row[k] is None for k in required):
                        raise ValueError(f"{path}:{line}: completed run is missing required measurements.")
                    population = ("n_vectors", "n_queries", "k") if kind == "retrieval" else ("n_examples",)
                    if any(row[k] <= 0 for k in population) or row["seed"] is None:
                        raise ValueError(f"{path}:{line}: completed run needs a seed and positive population counts.")
                    if kind == "retrieval" and row["k"] > row["n_vectors"]:
                        raise ValueError(f"{path}:{line}: k exceeds the indexed vector count.")
                    if kind == "models":
                        if row["qa_accuracy"] is None and row["count_mae"] is None:
                            raise ValueError(f"{path}:{line}: record a task quality metric.")
                        if row["grounded_claim_rate"] is not None and not row["n_claims_reviewed"]:
                            raise ValueError(f"{path}:{line}: grounding needs a positive reviewed-claim count.")
                low, high = ("search_p50_ms", "search_p95_ms") if kind == "retrieval" else ("latency_p50_s", "latency_p95_s")
                if row[low] is not None and row[high] is not None and row[low] > row[high]:
                    raise ValueError(f"{path}:{line}: p50 cannot exceed p95.")
            rows.append(row)
    return rows


def cohorts(rows, keys, frozen):
    groups = defaultdict(list)
    for row in rows:
        if row.get("status", "completed") == "completed":
            groups[tuple(row[k] for k in keys)].append(row)
    for key, members in groups.items():
        if any(len({r[field] for r in members}) != 1 for field in frozen):
            raise ValueError(f"Cohort {key} mixes incompatible {', '.join(frozen)}; use separate cohort IDs.")
    return groups


def save_figure(fig, directory, name, plt):
    fig.savefig(directory / (name + ".png"), dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(directory / (name + ".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return name + ".png"


def design_chart(directory, plt):
    from matplotlib.patches import FancyBboxPatch
    fig, ax = plt.subplots(figsize=(12, 4.2))
    ax.set(xlim=(0, 12), ylim=(0, 4))
    ax.axis("off")
    ax.text(.15, 3.65, "ConstAnt experiment design", fontsize=20, weight="bold", color="#28372e")
    ax.text(.15, 3.25, "PLANNED STUDY — no benchmark or fine-tuning results yet", fontsize=10, color="#6c7b70")
    items = [
        ("1. Freeze evaluation", "Reviewed labels\nGrouped data splits\nSource / prompt hashes"),
        ("2. Compare retrieval", "FAISS FlatIP reference\nHNSW / IVF candidates\nFixed vectors and queries"),
        ("3. Compare models", "Original Instruct vs QLoRA\nIdentical evidence inputs\nFixed inference budgets"),
        ("4. Test the app", "Freeze chosen retriever\nMeasure end-to-end QA\nReport time and memory"),
    ]
    for index, (title, body) in enumerate(items):
        x = .15 + index * 3
        ax.add_patch(FancyBboxPatch((x, .9), 2.65, 1.85, boxstyle="round,pad=0.08,rounding_size=0.12", facecolor="#edf2e9", edgecolor="#cad7c6"))
        ax.text(x + .14, 2.33, title, fontsize=11, weight="bold", color="#355f48")
        ax.text(x + .14, 1.85, body, va="top", fontsize=10, linespacing=1.7, color="#28372e")
        if index < 3:
            ax.annotate("", xy=(x + 2.95, 1.8), xytext=(x + 2.75, 1.8), arrowprops={"arrowstyle": "->", "color": "#6c7b70"})
    ax.text(.15, .3, "Keep index effects separate from adapter effects. Log failures and unmeasured metrics explicitly.", fontsize=10, color="#6c7b70")
    fig.tight_layout()
    return save_figure(fig, directory, "experiment-design", plt)


def metric_chart(rows, metrics, title, directory, name, plt):
    fig, axes = plt.subplots(2, 2, figsize=(13, max(6, len(rows) * .65 + 3)))
    for ax, (field, label) in zip(axes.flat, metrics):
        points = [(i, row[field]) for i, row in enumerate(rows) if row[field] is not None]
        ax.set_yticks(range(len(rows)), [r["run_id"] for r in rows], fontsize=8)
        ax.set_ylim(len(rows) - .5, -.5)
        ax.set_title(label, fontsize=11)
        ax.grid(axis="x", alpha=.18)
        if field in RATES:
            ax.set_xlim(-.03, 1.03)
        else:
            ax.set_xlim(left=0)
        if points:
            ax.scatter([v for _, v in points], [i for i, _ in points], color="#416e55", s=44, zorder=3)
        else:
            ax.text(.5, .5, "Not reported", transform=ax.transAxes, ha="center", color="#6c7b70")
    fig.suptitle(title + "\nEach point is one recorded run; missing metrics are omitted.", fontsize=13)
    fig.tight_layout()
    return save_figure(fig, directory, name, plt)


def markdown_table(rows, columns):
    def cell(value):
        if value is None or value == "":
            return "—"
        text = f"{value:.5g}" if isinstance(value, float) else str(value)
        return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
    return "\n".join(["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |",
                       *["| " + " | ".join(cell(row[c]) for c in columns) + " |" for row in rows]])


def generate(results_dir=ROOT / "results", output_dir=ROOT):
    data = {kind: read_results(Path(results_dir), kind) for kind in SCHEMAS}
    retrieval = cohorts(data["retrieval"], ("cohort_id",), ("n_vectors", "n_queries", "k"))
    models = cohorts(data["models"], ("cohort_id", "task"), ("n_examples", "retrieval_run_id"))
    training = cohorts(data["training_steps"], ("run_id",), ("adapter_id",))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    charts, reports = output_dir / "charts", output_dir / "reports"
    charts.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    design_chart(charts, plt)
    lines = ["# Experiment comparison", "", "Generated UTC: " + datetime.now(timezone.utc).isoformat(timespec="seconds"), "",
             "Inputs: `retrieval.csv`, `models.csv`, `training_steps.csv`. Only completed runs are compared; training curves use actual logged steps.", "",
             "![Planned experiment design](../charts/experiment-design.png)", ""]
    if not retrieval and not models and not training:
        lines += ["**No measured comparison results yet.** The design chart describes planned work; it is not a performance chart.", ""]
    for (cohort,), rows in sorted(retrieval.items()):
        image = metric_chart(rows, [("ann_recall_at_k", "ANN recall@k (higher is better)"), ("relevance_recall_at_k", "Judged relevance recall@k (higher is better)"),
                                   ("search_p95_ms", "p95 index search, ms (lower is better)"), ("index_size_mib", "Saved index, MiB (lower is smaller)")],
                             f"Retrieval cohort: {cohort}", charts, "retrieval-" + cohort, plt)
        lines += ["## Retrieval: " + cohort, "", f"{rows[0]['n_vectors']} vectors; {rows[0]['n_queries']} measured queries; k={rows[0]['k']}.", "",
                  markdown_table(rows, ["run_id", "index", "seed", "ann_recall_at_k", "relevance_recall_at_k"]), "",
                  markdown_table(rows, ["run_id", "search_p50_ms", "search_p95_ms", "build_seconds", "peak_rss_mib", "index_size_mib"]), "",
                  f"![Retrieval measurements](../charts/{image})", ""]
    for (cohort, task), rows in sorted(models.items()):
        image = metric_chart(rows, [("qa_accuracy", "Task accuracy (higher is better)"), ("count_mae", "Count MAE, objects (lower is better)"),
                                   ("latency_p95_s", "p95 complete request, seconds (lower is better)"), ("peak_vram_gib", "Peak allocated GPU memory, GiB")],
                             f"Model cohort: {cohort} / {task}", charts, f"models-{cohort}-{task}", plt)
        lines += [f"## Models: {cohort} / {task}", "", markdown_table(rows, ["run_id", "model_variant", "adapter_id", "retrieval_run_id", "n_examples", "n_claims_reviewed", "qa_accuracy", "count_mae", "grounded_claim_rate"]), "",
                  markdown_table(rows, ["run_id", "latency_p50_s", "latency_p95_s", "peak_vram_gib", "output_tokens_per_s"]), "",
                  f"![Model measurements](../charts/{image})", ""]
        if len({row["model_variant"] for row in rows}) < 2:
            lines += ["Only one model variant has measurements in this cohort; no baseline-versus-QLoRA conclusion is available.", ""]
    for (run,), rows in sorted(training.items()):
        rows = sorted(rows, key=lambda row: row["step"])
        fig, ax = plt.subplots(figsize=(9, 4))
        for field, label in (("train_loss", "Training loss"), ("eval_loss", "Validation loss")):
            points = [r for r in rows if r[field] is not None]
            if points:
                ax.plot([r["step"] for r in points], [r[field] for r in points], marker="o", label=label)
        ax.set(title="Logged losses: " + run, xlabel="Optimizer step", ylabel="Loss")
        ax.grid(alpha=.2)
        ax.legend()
        fig.tight_layout()
        image = save_figure(fig, charts, "training-" + run, plt)
        lines += ["## Training: " + run, "", f"{len(rows)} logged steps for adapter `{rows[0]['adapter_id']}`. Missing losses are not zero-filled; lines connect recorded observations only.", "",
                  f"![Logged training losses](../charts/{image})", ""]
    for kind in ("retrieval", "models"):
        other = [r for r in data[kind] if r["status"] != "completed"]
        if other:
            lines += ["## Not completed: " + kind, "", markdown_table(other, ["run_id", "status", "details_file"]), ""]
    lines += ["## Interpretation limits", "", "Cohorts must have matching frozen manifests. This tool checks schema, numeric ranges, counts and selected cohort fields; it cannot verify source labels or reproduce a manually entered measurement.", "",
              "Individual runs are not pooled into significance claims. Use the run reports and raw outputs for paired/source-group analysis. Measured retrieval fidelity does not establish answer accuracy, and a lower training loss does not establish a better construction assistant.", ""]
    summary = reports / "summary.md"
    summary.write_text("\n".join(lines), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(generate(args.results_dir, args.output_dir))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f"Report not generated: {exc}\n")
