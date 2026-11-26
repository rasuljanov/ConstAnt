# Experiment plan

Created: 2026-11-18. All configurations below are proposals until a completed run records them.

## Questions to answer

1. With identical embeddings and corpus, what do FAISS indexes trade in retrieval fidelity, relevance, time, and memory?
2. With identical inputs and evidence, does QLoRA improve construction-task accuracy or reduce unsupported claims?
3. With a fixed chosen retriever, does the complete application improve enough to justify its latency and operating cost?

Here **baseline** means the original **Qwen/Qwen3-VL-4B-Instruct**, without an adapter. It does not mean a separate pretrained Base checkpoint. Start from the app's pinned revision `ebb281ec70b05090aa6165b016eac8ec08e71b17`; verify it again when freezing a run. Both model variants should use the same NF4/FP16 inference configuration for the primary comparison. A full-precision comparison is a separate ablation.

ConstAnt now defaults to a WSL vLLM FP16 server. The optional Transformers profile defaults to NF4 and also supports FP16. Keep both the engine and precision fixed for baseline-versus-adapter comparisons. Evaluate engine changes separately; the [vLLM integration validation](reports/vllm-validation.md) does not establish a speed or accuracy improvement. Its API timings include request/queue time and do not measure per-request peak GPU memory.

## Study order

| Stage | Conditions | What stays fixed |
| --- | --- | --- |
| Retrieval only | FlatIP reference, HNSWFlat, IVFFlat; IVFPQ optional | Embedding model/revision, vectors, queries, normalization, filters, k, CPU threads, hardware |
| Model only | Unchanged Instruct; same checkpoint with QLoRA adapter | Questions, retrieved chunk IDs/order/text, crops, frame times, prompt, tools, decoding, precision |
| Application | Baseline and QLoRA with no retrieval, exact retrieval, and selected ANN retrieval | Test split and complete processing budgets; label each retrieval condition explicitly |

Select index parameters and adapter checkpoints using validation data. Open the frozen test set only after those decisions. A joint model/retrieval gain must not be reported as a fine-tuning-only gain.

## Retrieval design: FAISS + PostgreSQL

PostgreSQL is the source of truth for assets, chunks, provenance, measurements, and stable vector IDs. FAISS holds searchable vectors referencing those IDs. Raw images/videos/3D files remain in asset storage. Keep an index generation ID and corpus/vector manifest so the database and saved index can be verified together.

Start with text chunks from documents/logs and timestamped/tiled visual descriptions. Retrieve the actual image crop or frame as evidence when needed. These text embeddings are not direct image embeddings. Treat a changed captioner or embedding model as a new corpus/cohort.

For the first text-embedding candidate, evaluate `intfloat/multilingual-e5-small` (384 dimensions). Pin its revision and record its query/passage prefixes, normalization, chunk length, overlap, and language coverage. Keep the generator model fixed during index experiments. Embeddings and vector search can initially run on CPU, leaving the GPU for Qwen; measure rather than assume performance.

Normalize both corpus and query vectors when comparing cosine similarity using inner product. Use FlatIP on the same eligible corpus as the exact reference. ANN recall measures overlap with that reference; it does not measure whether the returned evidence answers a human question. Review relevance separately. Record tie handling and deduplicate chunk IDs before scoring.

| Index | Candidate exploration | Notes |
| --- | --- | --- |
| FlatIP | Exact reference, k = 5/10/20 as separate conditions | No index training; establishes exact neighbors |
| HNSWFlat | M = 16/32; efSearch = 32/64/128; record efConstruction | Record each configuration separately; plan a rebuild/tombstone policy because FAISS HNSW does not support normal vector removal |
| IVFFlat | Tune nlist and nprobe on validation data | Train the coarse quantizer only on the permitted index-training corpus; record sampled IDs and seed |
| IVFPQ | Optional memory/compression study | Only when corpus size supports quantizer training; record nlist/nprobe, PQ subquantizers, bits, and reconstruction/reranking settings |

These are candidate sweeps, not proven optimal settings. Small construction corpora may not benefit from ANN or support meaningful IVF/PQ training. Report an index as skipped with a reason rather than duplicating vectors to make it look scalable.

Test date/site/asset filters explicitly. Exact and approximate runs must search the same eligible corpus. Naive global top-k followed by filtering can miss valid neighbors; document any oversampling or per-scope index strategy and include its latency. Also check deletion, reindexing, saved-index reload, stale-ID handling, and PostgreSQL/FAISS synchronization.

## Data and reference answers

- Label image crops with checked class counts and answerable scene questions. Document class definitions and ambiguous/occluded objects. Site-wide totals require a complete tiling/counting protocol, not top-k retrieval.
- Label video questions with supported timestamps and temporal coverage. Keep complete source recordings together across splits; neighboring clips/frames can leak the same scene.
- Derive PM numerical reference answers using reviewed Python/SQL calculations. Score units, source scope, measured versus filename altitude, and timestamps. RAG retrieval does not replace full-table maxima or aggregation.
- Include text/log QA, questions in the intended languages, follow-ups, and deliberately unanswerable requests. Preserve uncertainty in references; historical sensor readings are not a compliance verdict.
- Keep duplicates, overlapping tiles, adjacent frames, and all examples derived from one flight/site capture in the same group. For a single orthophoto, use separated spatial blocks with a buffer when constructing a spatial holdout and state the remaining same-site limitation.
- The supplied PM collection is from one date. Do not claim unseen-day generalization from a random row split; obtain additional dates/sites for that claim.

Freeze train/validation/test group IDs and source hashes before creating fine-tuning examples. Do not use test answers to tune prompts, chunks, index parameters, adapters, or report wording. For retrieval tests it is legitimate for the searchable knowledge corpus to contain held-out reference documents needed to answer a query; keep evaluation questions/answers out of the corpus and distinguish corpus availability from training exposure. For a strict unseen-site model test, keep held-out captures out of fine-tuning entirely.

## QLoRA study on the RTX 5000 16 GB

Use reviewed multimodal instruction/answer pairs; raw CSV uploads are not automatically supervised VLM training examples. Use checked tool results as evidence for table QA, and mask labels for prompt/visual tokens as required by the chosen collator. Keep raw questions, image/frame references, answer labels, and group IDs traceable.

Begin with a small feasibility run: NF4 frozen weights, FP16 compute, gradient checkpointing, microbatch 1, and a conservative visual/token budget. Measure actual training VRAM before scaling; inference fit does not prove training fit. Do not run the app's GPU worker and training simultaneously. WSL2/Linux is a deployment option to evaluate if the chosen training stack has Windows issues, not an installation already completed.

Candidate adapter ranks are 8 and 16. Record actual target module names, alpha, dropout, optimizer, learning rate/schedule, effective batch size, epochs/steps, seed, data revision, preprocessing, and trainable parameter count. Verify which language/vision/projector parameters are frozen; do not guess module names or enable every module by default. Pick the checkpoint on validation-task metrics, with validation loss as supporting evidence.

Evaluate the baseline first. For an isolated model comparison, save and replay identical evidence bundles for both variants, including the same numeric tool outputs and ordered visual frames. Evaluate planner/tool selection separately, then evaluate the complete pipeline with its actual model-call counts. Equal prompts alone do not guarantee equal evidence. Start with seed 42; where feasible repeat adapter training and index construction with seeds 43 and 44 and keep results separate.

## Measurements and charts

| Area | Measurements | Planned charts |
| --- | --- | --- |
| Retrieval | ANN recall@k against exact neighbors; judged relevance recall@k; p50/p95 search time; build time; peak process RSS; index bytes | Recall, relevance, latency, and index size per frozen cohort |
| Model | Task accuracy; count MAE; grounded-claim fraction; p50/p95 end-to-end latency; peak allocated GPU memory; generation throughput | Quality and resource use, baseline versus QLoRA |
| Training | Actual training and validation loss at recorded steps | Loss versus step per training run |

ANN recall@k = mean exact-neighbor overlap / k. Relevance recall@k = relevant retrieved chunks / all judged relevant eligible chunks, averaged only over queries with a nonempty relevant set. Report query exclusions and the annotation scope. Task accuracy requires the task's entire rubric to pass. Count MAE uses checked count examples. Grounded-claim rate uses independently reviewed supported claims / reviewed factual claims; do not treat a model's own self-rating as ground truth.

Time embedding, index search, metadata fetch, preprocessing, prefill/generation, and full request separately in raw logs. `search_p95_ms` excludes embedding and SQL fetch unless the cohort explicitly defines otherwise. Model latency fields cover the whole request after the agreed load/warmup policy. Keep cold-start/model-load measurements separate from warm requests; disclose cache and batch/concurrency policy. Report failed requests and OOMs instead of dropping them from the study.

Use identical test items for paired model comparisons. For uncertainty, bootstrap by independent source group when there are enough groups; seed-to-seed variation is not a confidence interval over sites. With few independent groups, report descriptive results and limitations. The reporting script plots individual recorded runs and makes no significance claims.

## Next executable work

1. Create reviewed evaluation questions and split manifests; freeze a cohort record.
2. Implement the PostgreSQL chunk/vector-ID schema and FAISS FlatIP baseline, then validate retrieval relevance and lifecycle synchronization.
3. Add HNSW/IVF benchmark runners that export measured rows to `results/retrieval.csv`.
4. Add a model evaluation runner and adapter-loading path; record baseline outputs before training.
5. Run the QLoRA feasibility/training experiment, evaluate the selected adapter on the same frozen test set, and regenerate the charts/report.

None of these runners or database migrations is implemented by the notes/reporting folder itself.

## Primary references

- [FAISS index selection and index limitations](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index)
- [FAISS cosine similarity and normalization](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances)
- [Multilingual E5-small model card](https://huggingface.co/intfloat/multilingual-e5-small)
- [PEFT quantized-model training](https://huggingface.co/docs/peft/developer_guides/quantization)
- [QLoRA paper](https://arxiv.org/abs/2305.14314)

Record installed package versions and tested settings in each run; documentation examples alone are not proof that a Qwen VLM training configuration fits this GPU.
