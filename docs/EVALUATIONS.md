# AI Evaluation Status (`update.md` §10)

## Deterministic retrieval and evidence gate

`evals/runners/run_evals.py` calls the production `hybrid_rank`, `_extractive_claims`, and citation validator over the versioned `evals/datasets/grounded_qa_v2.jsonl` corpus. The 12 cases cover direct support, ranking among distractors, method/dataset extraction, contradictory sources, hyphenated acronyms, title-only false support, no-answer and underspecified questions, prompt injection, and multi-sentence abstracts. A separate negative control verifies that a fabricated citation is rejected.

Run from the repository root:

```bash
python evals/runners/run_evals.py
```

The gate prints case-level checks and aggregate metrics, and exits nonzero when any case or metric threshold fails.

| Metric | Minimum threshold |
|---|---:|
| Abstention accuracy | 100% |
| Citation validity (IDs exist in retrieved set) | 100% |
| Exact sentence support for emitted claims | 100% |
| Answerable-case claim coverage | 90% |
| Recall@5 for labeled relevant sources | 90% |
| MRR@5 for labeled relevant sources | 90% |

### Current measured baseline

On 2026-11-08 with the current production selector and ranker:

| Result | Measured |
|---|---:|
| Cases | 12 |
| Passing cases | 12 / 12 |
| Abstention accuracy | 100% |
| Citation validity | 100% |
| Exact sentence support | 100% |
| Answerable-case claim coverage | 100% |
| Recall@5 | 100% |
| MRR@5 | 100% |
| Fabricated-citation negative control | Pass |
| Gate | **Pass** |

The gate passes after BM25 ignores common question terms, claim selection requires substantive overlap and relevant query entities, and instruction-like abstract sentences are excluded. Do not weaken these cases. The corpus remains small and hand-authored, so passing it is a regression check rather than a broad research-quality result.

## What this suite does not prove

This is a deterministic regression gate, not a broad research-quality benchmark. The corpus is small and hand-authored; the suite does not measure scientific correctness, calibrated confidence, statistical significance, provider/model behavior, project authorization, deployed-service behavior, latency, or cost. Exact-sentence matching is appropriate for the current extractive selector and must be replaced with claim-level evidence-span evaluation before generated synthesis is enabled. Add larger independently labeled datasets and a separate staging smoke before using the results as a production quality claim.

See [STATUS.md](STATUS.md) for remaining release blockers and current local validation.
