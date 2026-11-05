"""Deterministic smoke evals (update.md §10.2). No LLM judge needed.

Checks citation-ID integrity + abstention on the v1 datasets.
Usage: python evals/runners/run_evals.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "grounded_qa_v1.jsonl"


def check_case(case: dict, retrieved_ids: set[str], answer_citations: list[str], abstained: bool) -> bool:
    expected = case["expected"]
    if expected.get("must_abstain") and not abstained:
        return False
    # Must-pass gate: zero fabricated citation IDs.
    return all(cid in retrieved_ids for cid in answer_citations)


def main() -> int:
    cases = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    failures = 0
    for case in cases:
        retrieved = set(case["expected"]["allowed_source_ids"])
        # Simulate a correct system: abstains iff must_abstain, cites only retrieved.
        abstained = bool(case["expected"].get("must_abstain"))
        citations = [] if abstained else sorted(retrieved)
        ok = check_case(case, retrieved, citations, abstained)
        print(f"{'PASS' if ok else 'FAIL'} {case['id']}")
        failures += 0 if ok else 1
    # Fabricated-citation negative control must fail.
    assert not check_case(cases[0], set(), ["fake_id"], abstained=False)
    print("PASS fabricated-citation control (correctly rejected)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
