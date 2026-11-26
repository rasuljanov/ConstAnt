"""Synthetic test measurements live only in pytest temporary directories."""

import csv

import pytest

from notes.generate_report import SCHEMAS, generate, read_results


def write_log(directory, kind, rows):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (kind + ".csv")).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCHEMAS[kind])
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def inputs(tmp_path):
    directory = tmp_path / "results"
    for kind in SCHEMAS:
        write_log(directory, kind, [])
    return directory


def retrieval(run="test-flat"):
    return {"run_id": run, "cohort_id": "test-corpus", "index": "flat_ip", "index_parameters": "{}",
            "seed": 42, "n_vectors": 100, "n_queries": 10, "k": 5, "ann_recall_at_k": 1,
            "search_p50_ms": 1, "search_p95_ms": 2, "status": "completed"}


def model(run="test-baseline", variant="baseline"):
    return {"run_id": run, "cohort_id": "test-evidence", "task": "table_qa", "model_variant": variant,
            "adapter_id": "test-adapter" if variant == "qlora" else "", "retrieval_run_id": "test-flat",
            "seed": 42, "n_examples": 10, "qa_accuracy": .5, "latency_p95_s": 2,
            "peak_vram_gib": 4, "status": "completed"}


def test_empty_inputs_make_only_an_explicitly_planned_design(inputs, tmp_path):
    output = tmp_path / "output"
    summary = generate(inputs, output)
    assert "No measured comparison results yet" in summary.read_text(encoding="utf-8")
    assert (output / "charts/experiment-design.png").read_bytes().startswith(b"\x89PNG")
    assert (output / "charts/experiment-design.svg").is_file()
    assert len(list((output / "charts").glob("*.png"))) == 1
    assert all(read_results(inputs, kind) == [] for kind in SCHEMAS)


def test_measured_logs_render_per_cohort_and_preserve_missing_metrics(inputs, tmp_path):
    approximate = {**retrieval("test-hnsw"), "index": "hnsw", "ann_recall_at_k": .8}
    write_log(inputs, "retrieval", [retrieval(), approximate])
    adapted = {**model("test-qlora", "qlora"), "qa_accuracy": .7}
    write_log(inputs, "models", [model(), adapted])
    write_log(inputs, "training_steps", [
        {"run_id": "test-training", "adapter_id": "test-adapter", "step": 1, "train_loss": 2},
        {"run_id": "test-training", "adapter_id": "test-adapter", "step": 2, "train_loss": 1, "eval_loss": 1.2},
    ])
    assert read_results(inputs, "models")[0]["count_mae"] is None
    output = tmp_path / "output"
    summary = generate(inputs, output).read_text(encoding="utf-8")
    for name in ("retrieval-test-corpus", "models-test-evidence-table_qa", "training-test-training"):
        assert (output / "charts" / (name + ".png")).is_file()
        assert (output / "charts" / (name + ".svg")).is_file()
    assert "test-qlora" in summary and "0.7" in summary and "—" in summary
    assert "statistical significance" not in summary and "winner" not in summary


@pytest.mark.parametrize("changes", [
    {"ann_recall_at_k": 1.1}, {"search_p95_ms": "NaN"}, {"index_size_mib": "inf"},
    {"search_p50_ms": 3}, {"k": 101}, {"n_queries": 0}, {"seed": ""},
    {"run_id": "../outside"}, {"index_parameters": "[]"}, {"status": "success"},
    {"details_file": "../../outside.md"},
])
def test_invalid_measurements_are_rejected(inputs, changes):
    write_log(inputs, "retrieval", [{**retrieval(), **changes}])
    with pytest.raises(ValueError):
        read_results(inputs, "retrieval")


def test_duplicate_runs_and_incompatible_cohorts_are_rejected(inputs, tmp_path):
    write_log(inputs, "retrieval", [retrieval(), retrieval()])
    with pytest.raises(ValueError, match="duplicate"):
        read_results(inputs, "retrieval")
    write_log(inputs, "retrieval", [retrieval(), {**retrieval("test-other"), "k": 10}])
    with pytest.raises(ValueError, match="incompatible"):
        generate(inputs, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_models_cannot_mix_evidence_or_mislabel_an_adapter(inputs, tmp_path):
    write_log(inputs, "models", [{**model(), "adapter_id": "test-adapter"}])
    with pytest.raises(ValueError, match="adapter"):
        read_results(inputs, "models")
    write_log(inputs, "models", [model(), {**model("test-qlora", "qlora"), "retrieval_run_id": "different-evidence"}])
    with pytest.raises(ValueError, match="incompatible"):
        generate(inputs, tmp_path / "output")


def test_grounding_requires_a_denominator_and_training_steps_must_be_unique(inputs):
    write_log(inputs, "models", [{**model(), "grounded_claim_rate": .8}])
    with pytest.raises(ValueError, match="reviewed-claim"):
        read_results(inputs, "models")
    step = {"run_id": "test-training", "adapter_id": "test-adapter", "step": 1, "train_loss": 2}
    write_log(inputs, "training_steps", [step, step])
    with pytest.raises(ValueError, match="duplicate"):
        read_results(inputs, "training_steps")


def test_failed_and_planned_runs_are_reported_without_result_charts(inputs, tmp_path):
    write_log(inputs, "retrieval", [{**retrieval("test-failed"), "status": "failed"},
                                    {**retrieval("test-planned"), "status": "planned"}])
    output = tmp_path / "output"
    report = generate(inputs, output).read_text(encoding="utf-8")
    assert "No measured comparison results yet" in report
    assert "test-failed" in report and "test-planned" in report
    assert not list((output / "charts").glob("retrieval-*"))
