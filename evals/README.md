# Evals (update.md §10)

The deterministic CI gate runs versioned dataset `grounded_qa_v3` against the
production hybrid ranker and extractive claim selector. It has 18 hand-authored
cases covering relevant-source ranking, supported and unsupported questions,
exact sentence support, multiple-source findings, conflicting findings,
causality wording, numeric results, acronym/entity/benchmark disambiguation,
prompt injection, and abstention. The runner checks citation IDs against the
retrieved set and source text, allowed citations, expected ranking, required and
forbidden phrases, claim counts, and abstention. It also reports abstention
accuracy, exact support, answer coverage, Recall@5, and MRR@5, with a fabricated
citation negative control.

These synthetic fixtures measure deterministic retrieval and verbatim evidence
selection only. They do not establish scientific correctness, PDF/page-level
evidence quality, synthesis quality, deployed provider behavior, or production
tenant isolation (covered separately by backend security tests and staging
checks). No production user data is included. `grounded_qa_v2.jsonl` remains the
prior 12-case dataset version.

Run: `python evals/runners/run_evals.py`
