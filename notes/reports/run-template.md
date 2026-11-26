# Run: <run_id>

Status: planned / completed / failed / skipped

## Purpose and frozen comparison

- Run ID, cohort ID, task and UTC start/end:
- Hypothesis / single factor being changed:
- Baseline / comparison run IDs:
- Source IDs + SHA-256 manifest; corpus/vector/query/reference-answer hashes:
- Train/validation/test group manifests; duplicate/overlap checks; held-out scope:
- Raw predictions, retrieved IDs/scores, tool results and timing log paths:

## Environment

- GPU / VRAM / driver; CPU / RAM; OS or WSL/Linux:
- Python, PyTorch, CUDA runtime, Transformers, PEFT, bitsandbytes, FAISS, PostgreSQL versions:
- Code snapshot/hash and dirty state; seed(s); CPU threads; concurrency:
- Cold/warm cache, model-load policy, warmup count, measured repeats:

## Retrieval (when applicable)

- Embedding model/revision, dimension/dtype, query/passage prefixes, normalization:
- Captioner revision and prompt if visual descriptions are indexed:
- Chunking, overlap, stable vector-ID mapping and index generation ID:
- FAISS index class, metric and full parameters; IVF/PQ training IDs and seed:
- k; source/date/site filters; exact-reference construction and tie handling:
- Judged relevance set, exclusions, zero-relevance queries and score definitions:
- Database/index synchronization, deletion and index-reload checks:

## Model and QLoRA (when applicable)

- Base model/revision (unchanged Instruct or same checkpoint + adapter):
- Adapter ID/path/hash; target modules; frozen/trainable modules/count:
- NF4 / double quantization / FP16 configuration; merged or unmerged adapter:
- Rank/alpha/dropout; optimizer/LR/scheduler; epochs/steps; effective batch:
- Training data revision; collator/label masking; checkpoint selection rule:
- System/user prompts and hashes; ordered evidence snapshot/hash; tools:
- Tile/crop pixel coordinates, image sizes, frame timestamps, input/output token budgets:
- Decoding; truncation; failed calls; measured peak allocated and reserved GPU memory:

## Results and interpretation

- CSV row(s) and denominators; task-specific scoring rubric:
- Paired examples improved / worsened / unchanged, with evidence:
- Failure/OOM count and cause; retried requests and whether latency includes retries:
- Build/search/preprocessing/prefill/generation/complete-request timing boundaries:
- Claim-grounding review process and reviewer; relevant chart paths:
- Validation decisions versus final test results:
- Limitations, uncertainty and whether the evidence supports the hypothesis:
- Next decision (retain / tune on validation / reject / collect more data):

Do not enter expected outcomes as measured results. Mark inapplicable sections explicitly.
