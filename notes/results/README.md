# Measurement logs

Files start with headers only. Append actual measurements; use a blank for an unmeasured metric. Never substitute zero for missing results.

`status` is `planned`, `completed`, `failed`, or `skipped`. Only completed runs produce result charts. Keep failures/skips in the logs and describe them in the linked run report. IDs use letters, numbers, underscores, or hyphens; use an existing report path relative to `notes`, such as `reports/retrieval-001.md`.

## Cohorts

A `cohort_id` names one frozen comparison protocol, not simply a date. Its run report must identify corpus/vector/query hashes, relevant judgments, eligible filters, k, hardware, thread/batch policy and timing boundaries. The generator checks counts/k within retrieval cohorts, but cannot verify semantic equivalence of your manually recorded manifests.

For controlled model comparisons, a cohort must also freeze inputs, prompts, ordered evidence bundles, quantization, visual budget, token limits, tooling and decoding. `retrieval_run_id` identifies the fixed evidence condition (`none`, `oracle`, or a retrieval run ID). Different retrieved evidence belongs to a different controlled model cohort. Label joint end-to-end experiments separately in their run reports.

## `retrieval.csv`

One row per measured index configuration and seed. Times are milliseconds for search and seconds for build; memory/index sizes use MiB (bytes / 2^20). Rates are fractions from 0 to 1. `index_parameters` is a JSON object inside the CSV field; use a CSV writer or quote embedded double quotes correctly. `n_queries` is the measured search workload count; explain repetitions and excluded relevance judgments in the report. `ann_recall_at_k` and `search_p95_ms` are required for completed runs.

## `models.csv`

One row per model variant, task, cohort and evaluation repeat. `model_variant` is `baseline` or `qlora`; a completed QLoRA row must name its `adapter_id`. `n_examples` is the evaluated task population. Accuracy/grounding are fractions; `count_mae` is objects per checked count example; latency is seconds; GPU memory is GiB (bytes / 2^30). A grounded-claim rate requires a positive `n_claims_reviewed` denominator. Record at least one task-quality metric plus p95 request latency and peak VRAM for a completed model run.

Use the app's `wall_seconds` for request latency. Its `inference_seconds` and `output_tokens_per_second` are per model call; do not silently treat a final synthesis call as the whole planner/retrieval/answer pipeline. Benchmark scripts must establish the declared timing boundaries.

## `training_steps.csv`

One row per actual logged optimizer step and training run. Missing train/eval loss stays blank; at least one loss is required on each row. Step IDs must be unique within a run, and the adapter ID must remain consistent. Record training setup, wall time, validation selection and trainable modules in the run report. Do not invent a baseline training-loss curve for an untrained model.
