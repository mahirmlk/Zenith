"""Run the real deterministic retrieval/evidence path on a fixed corpus.

This smoke eval uses the same hybrid ranker and extractive claim selector as
the API. It intentionally does not assess broader scientific correctness.
Usage: python evals/runners/run_evals.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "grounded_qa_v1.jsonl"
sys.path.insert(0, str(ROOT / "backend"))

from routers.research import _extractive_claims  # noqa: E402
from security.output_validation import validate_citations  # noqa: E402
from services.retrieval import hybrid_rank  # noqa: E402


def evaluate_case(case: dict) -> tuple[bool, set[str], list[str], bool]:
    corpus = case.get("corpus", [])
    ranked = hybrid_rank(case["question"], corpus)[:5]
    claims = _extractive_claims(case["question"], ranked)
    retrieved_ids = {str(paper["id"]) for paper in ranked if paper.get("id")}
    citations = [
        citation
        for claim in claims
        if (match := re.search(r"\[([A-Za-z0-9_\-:.]+)\]$", claim))
        for citation in [match.group(1)]
    ]
    abstained = not claims
    expected = case["expected"]
    fabricated = validate_citations(" ".join(claims), retrieved_ids)
    source_gate = set(citations).issubset(set(expected.get("allowed_source_ids", [])))
    expected_abstention = expected.get("must_abstain") == abstained
    return not fabricated and source_gate and expected_abstention, retrieved_ids, citations, abstained


def main() -> int:
    cases = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    failures = 0
    for case in cases:
        ok, _retrieved, citations, abstained = evaluate_case(case)
        print(f"{'PASS' if ok else 'FAIL'} {case['id']} abstained={abstained} citations={citations}")
        failures += 0 if ok else 1
    # Fabricated-citation negative control must fail.
    assert validate_citations("Unsupported claim [fake_id]", {"paper_a"}) == ["fake_id"]
    print("PASS fabricated-citation control (correctly rejected)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
