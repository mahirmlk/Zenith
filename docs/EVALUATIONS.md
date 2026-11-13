# AI Evaluation Status (`update.md` §10)

## Deterministic retrieval and evidence gate

`evals/runners/run_evals.py` calls the production hybrid ranker, extractive answer selector, PDF evidence selector, and citation validator. It runs `grounded_qa_v3` (18 abstract-grounded cases) and `pdf_evidence_v1` (6 PDF page-evidence cases). The PDF suite covers exact citation order and snippets, page-local span integrity, injection-only abstention, entity mismatch, and multiple matching pages. A separate negative control verifies that a fabricated citation is rejected.

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
| PDF citation accuracy, exact page spans, abstention, and forbidden-text safety | 100% each |

### Current measured baseline

Historical 2026-11-08 baseline (`grounded_qa_v2`):

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

Current local baseline on 2026-11-13:

| Dataset / metric | Measured |
|---|---:|
| `grounded_qa_v3` | 18 / 18 pass |
| Paper abstention, citation, exact support, coverage, Recall@5, MRR@5 | 1.000 each |
| `pdf_evidence_v1` | 6 / 6 pass |
| PDF citation accuracy, exact span rate, abstention, forbidden-text safety | 1.000 each |
| `cross_paper_synthesis_v1` mocked-provider contract cases | 3 / 3 pass |
| `research_plan_v1` deterministic plan-preview cases | 5 / 5 pass |
| `research_plan_v1` deterministic plan preview cases | 5 / 5 pass |
| Fabricated-citation negative control | Pass |

The gate passes after BM25 ignores common question terms, claim selection requires substantive overlap and relevant query entities, and instruction-like abstract sentences are excluded. Do not weaken these cases. The corpus remains small and hand-authored, so passing it is a regression check rather than a broad research-quality result.

## What this suite does not prove

`cross_paper_synthesis_v1` adds three mocked-provider contract fixtures to the runner: opposing evidence remains conflicting, one-source support is downgraded to uncertain, and fabricated evidence IDs are rejected. These fixtures exercise deterministic service validation, not live model behavior or scientific correctness.

`research_plan_v1` verifies deterministic route selection, static task steps, fixed bounds, and preview-only metadata. It does not evaluate a plan executor because execution is not implemented.

This is a deterministic regression gate, not a broad research-quality benchmark. The corpora are small and hand-authored; the suite does not measure scientific correctness, calibrated confidence, statistical significance, provider/model behavior, project-comparison quality, project authorization, deployed-service behavior, latency, or cost. Exact-sentence matching is appropriate for the extractive selectors. Synthesis needs independently labeled claim-level evidence-span evaluation, blinded domain-expert review, and staging/provider validation before production use. Add larger datasets and separate staging/human-review gates before using these results as a production quality claim.

See [STATUS.md](STATUS.md) for remaining release blockers and current local validation.
