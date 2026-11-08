# AI Evaluation Status (`update.md` §10)

## Current harness

`evals/runners/run_evals.py` is a deterministic fixture/checker smoke test over `evals/datasets/grounded_qa_v1.jsonl`. It currently constructs the retrieved IDs, citations, and abstention decision from the expected fixture fields, then checks citation-ID membership and one fabricated-ID negative control. It does **not** invoke Zenith retrieval, answer synthesis, or the backend API. Its passing cases are not a product quality baseline and must not be used as evidence of grounded-answer quality.

Run the checker with:

```bash
python evals/runners/run_evals.py
```

## Required before a release gate

- Invoke the same retrieval and answer code used by the application, with mocked external providers or a fixed local corpus.
- Version corpus, dataset, prompts, and model configuration alongside results.
- Measure retrieval recall/precision and claim-level citation support; test abstention, contradictory evidence, prompt injection, project scoping, and cross-tenant isolation.
- Record the first real baseline before setting thresholds. Retain run output as a CI artifact and document limitations.

Current evaluation coverage is smoke-only. See [STATUS.md](STATUS.md) for the release blockers.
