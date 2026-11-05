# Evals (update.md §10)

Deterministic smoke evals run in CI; full golden suite on release candidates.
`runners/run_evals.py` checks: (1) no fabricated citation IDs — every cited ID must exist in the retrieved set; (2) abstention on no-evidence cases; (3) cross-tenant access = 0 (backend security tests). Datasets are redistribution-safe public fixtures only; no production user data.
Run: `python evals/runners/run_evals.py`
