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
citation negative control. The same runner also executes `pdf_evidence_v1` (6
cases) against the production PDF page evidence selector. It checks exact
citation order, verbatim page spans and offsets, expected abstention, and
absence of forbidden instruction-like text; all four PDF metrics must equal
1.000.

`cross_paper_synthesis_v2` contains six mocked-provider contract cases: conflict
labeling, weak-support downgrade, fabricated generation anchors, unknown verifier
evidence IDs, incomplete assessments, and unsupported verifier claims downgraded
to uncertain. These fixtures test service contracts only; they do not evaluate
live provider behavior or scientific correctness.

`research_plan_v1` adds five deterministic preview cases covering task
classification, phrase-boundary false positives, source scope, bounded
ceilings, feature-gated synthesis steps, and the non-executing contract. It
does not establish that a multi-step executor exists or that the preview bounds
constrain separate API calls.

These synthetic fixtures do not establish broad PDF/page coverage, comparison
quality, synthesis quality, deployed provider behavior, or production tenant
isolation (covered separately by backend security tests and staging checks). No
production user data is included. `grounded_qa_v2.jsonl` remains the prior
12-case dataset version.

The watchlist smoke corpus includes an explicit single-token boundary check:
`cat` must not match `catalog`. This is a matcher contract fixture, separate
from the `important` relevance label. It currently exposes a substring false
positive in `_watchlist_matches`; the watchlist evaluation is expected to fail
until the token-boundary bug is fixed. The small corpus remains a smoke check,
not a human-calibrated relevance benchmark.

Run: `python evals/runners/run_evals.py`
