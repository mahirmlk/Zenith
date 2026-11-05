# Evaluations (update.md §10)

Harness: `evals/runners/run_evals.py` (deterministic, no LLM judge) over `evals/datasets/grounded_qa_v1.jsonl`. Gates: fabricated citation IDs = 0 (must-pass), abstention on no-evidence cases, cross-tenant access = 0 (backend security tests). Baseline (2026-11-05): smoke suite 3/3 PASS; backend suite 51 passed / 5 env-dependent failures (need OPENAI_API_KEY + live Supabase). Full golden suite (retrieval recall@k, grounded QA, comparison, red-team) is the `quality/ai-evals-and-ci` PR.
Run: `python evals/runners/run_evals.py`
