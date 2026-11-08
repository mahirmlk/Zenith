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
| Passing cases | 5 / 12 |
| Abstention accuracy | 91.7% |
| Citation validity | 100% |
| Exact sentence support | 100% |
| Answerable-case claim coverage | 100% |
| Recall@5 | 100% |
| MRR@5 | 94.4% |
| Fabricated-citation negative control | Pass |
| Gate | **Fail** |

The failing cases are `qa_rank_optimizer_001`, `qa_supported_dataset_001`, `qa_hyphenated_acronym_001`, `qa_title_only_001`, `qa_prompt_injection_001`, `qa_supported_robustness_001`, and `qa_crispr_disambiguation_001`. They expose these release findings: unrelated retrieved papers can contribute claims from generic query-term overlap; the selector emits a claim when only the title matches and the abstract does not support the question; a prompt-injection instruction in an abstract is emitted as a claim; and the CRISPR case ranks a generic editing-workflow paper above the relevant study. Do not weaken these cases to turn the suite green. Fix the retrieval/claim-selection behavior, then rerun and record the new baseline.

## What this suite does not prove

This is a deterministic regression gate, not a broad research-quality benchmark. The corpus is small and hand-authored; the suite does not measure scientific correctness, calibrated confidence, statistical significance, provider/model behavior, project authorization, deployed-service behavior, latency, or cost. Exact-sentence matching is appropriate for the current extractive selector and must be replaced with claim-level evidence-span evaluation before generated synthesis is enabled. Add larger independently labeled datasets and a separate staging smoke before using the results as a production quality claim.

See [STATUS.md](STATUS.md) for remaining release blockers and current local validation.
