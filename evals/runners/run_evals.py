"""Evaluate deterministic retrieval, abstention, citation, and support.

This hermetic gate calls the same hybrid ranker and extractive claim selector
as the API. It does not assess broad scientific correctness or deployed state.
Usage: python evals/runners/run_evals.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "grounded_qa_v2.jsonl"
DATASET_VERSION = "grounded_qa_v2"
TOP_K = 5
sys.path.insert(0, str(ROOT / "backend"))

from routers.research import _extractive_claims  # noqa: E402
from security.output_validation import validate_citations  # noqa: E402
from services.retrieval import hybrid_rank  # noqa: E402


def _claims_by_citation(claims: list[str]) -> list[tuple[str, str]]:
    parsed = []
    for claim in claims:
        match = re.search(r"\s+\[([A-Za-z0-9_\-:.]+)\]$", claim)
        if match:
            parsed.append((claim[: match.start()].strip(), match.group(1)))
        else:
            parsed.append((claim, ""))
    return parsed


def evaluate_case(case: dict) -> dict:
    corpus = case.get("corpus", [])
    ranked = hybrid_rank(case["question"], corpus)[:TOP_K]
    claims = _extractive_claims(case["question"], ranked)
    retrieved_ids = {str(paper["id"]) for paper in ranked if paper.get("id")}
    parsed_claims = _claims_by_citation(claims)
    citations = [citation for _text, citation in parsed_claims if citation]
    abstained = not claims
    expected = case["expected"]
    fabricated = validate_citations(" ".join(claims), retrieved_ids)
    allowed_citations = set(citations).issubset(set(expected.get("allowed_source_ids", [])))
    expected_abstention = expected.get("must_abstain") == abstained
    abstracts = {
        str(paper.get("id")): {
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", (paper.get("abstract") or "").strip())
            if sentence.strip()
        }
        for paper in corpus
        if paper.get("id")
    }
    supported_claim_count = sum(
        1 for text, citation in parsed_claims
        if citation in abstracts and text in abstracts[citation]
    )
    exact_support = supported_claim_count == len(claims) if claims else expected["must_abstain"]
    required_phrases = [phrase.casefold() for phrase in expected.get("required_claim_phrases", [])]
    claim_text = " ".join(text.casefold() for text, _citation in parsed_claims)
    required_claims_present = all(phrase in claim_text for phrase in required_phrases)
    forbidden_phrases = [phrase.casefold() for phrase in expected.get("forbidden_claim_phrases", [])]
    forbidden_claims_absent = not any(phrase in claim_text for phrase in forbidden_phrases)
    min_claims = expected.get("minimum_claims", 0 if expected["must_abstain"] else 1)
    claim_count_ok = len(claims) >= min_claims

    ranked_ids = [str(paper["id"]) for paper in ranked if paper.get("id")]
    gold_ids = expected.get("relevant_source_ids", [])
    reciprocal_rank = next(
        (1 / (rank + 1) for rank, paper_id in enumerate(ranked_ids) if paper_id in gold_ids),
        0.0,
    )
    recall = (
        len(set(ranked_ids).intersection(gold_ids)) / len(set(gold_ids))
        if gold_ids else None
    )
    expected_top_ids = expected.get("expected_top_ids", [])
    ranking_order_ok = ranked_ids[: len(expected_top_ids)] == expected_top_ids

    checks = {
        "abstention": expected_abstention,
        "citation_validity": not fabricated,
        "allowed_sources": allowed_citations,
        "exact_support": exact_support,
        "required_claims": required_claims_present,
        "forbidden_claims_absent": forbidden_claims_absent,
        "claim_count": claim_count_ok,
        "ranking_order": ranking_order_ok,
    }
    return {
        "id": case["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "ranked_ids": ranked_ids,
        "citations": citations,
        "abstained": abstained,
        "claim_count": len(claims),
        "supported_claim_count": supported_claim_count,
        "reciprocal_rank": reciprocal_rank if gold_ids else None,
        "recall_at_k": recall,
    }


def main() -> int:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cases) < 10:
        print(f"FAIL {DATASET_VERSION}: expected at least 10 cases, found {len(cases)}")
        return 1

    results = []
    for case in cases:
        result = evaluate_case(case)
        results.append(result)
        failed_checks = [name for name, passed in result["checks"].items() if not passed]
        label = "PASS" if result["passed"] else "FAIL"
        print(
            f"{label} {result['id']} abstained={result['abstained']} "
            f"ranked={result['ranked_ids']} citations={result['citations']}"
            + (f" failed={','.join(failed_checks)}" if failed_checks else "")
        )

    ranked_cases = [result for result in results if result["recall_at_k"] is not None]
    answerable_cases = [case for case in cases if not case["expected"]["must_abstain"]]
    abstention_correct = sum(result["checks"]["abstention"] for result in results) / len(results)
    citation_validity = sum(result["checks"]["citation_validity"] for result in results) / len(results)
    emitted_claim_count = sum(result["claim_count"] for result in results)
    support_validity = (
        sum(result["supported_claim_count"] for result in results) / emitted_claim_count
        if emitted_claim_count else 1.0
    )
    answer_coverage = sum(
        len(result["citations"]) > 0
        for result in results
        if result["id"] in {case["id"] for case in answerable_cases}
    ) / max(len(answerable_cases), 1)
    recall_at_k = sum(result["recall_at_k"] for result in ranked_cases) / max(len(ranked_cases), 1)
    mrr_at_k = sum(result["reciprocal_rank"] for result in ranked_cases) / max(len(ranked_cases), 1)

    # Independent negative control: a fabricated citation must be rejected.
    fabricated_rejected = validate_citations("Unsupported claim [fake_id]", {"paper_a"}) == ["fake_id"]
    print(f"{'PASS' if fabricated_rejected else 'FAIL'} fabricated-citation negative control")
    metrics = {
        "abstention_accuracy": abstention_correct,
        "citation_validity": citation_validity,
        "exact_support_rate": support_validity,
        "answerable_claim_coverage": answer_coverage,
        "recall_at_5": recall_at_k,
        "mrr_at_5": mrr_at_k,
    }
    thresholds = {
        "abstention_accuracy": 1.0,
        "citation_validity": 1.0,
        "exact_support_rate": 1.0,
        "answerable_claim_coverage": 0.9,
        "recall_at_5": 0.9,
        "mrr_at_5": 0.9,
    }
    for name, value in metrics.items():
        threshold = thresholds[name]
        print(f"METRIC {name}={value:.3f} threshold={threshold:.3f}")

    failures = sum(not result["passed"] for result in results)
    failed_metrics = [name for name, value in metrics.items() if value < thresholds[name]]
    if failed_metrics:
        print(f"FAILED METRIC GATES: {', '.join(failed_metrics)}")
    print(
        f"{DATASET_VERSION}: {len(results)} cases, "
        f"{len(results) - failures} passed, {failures} failed; "
        f"fabricated_citation_control={'PASS' if fabricated_rejected else 'FAIL'}"
    )
    return 1 if failures or failed_metrics or not fabricated_rejected else 0


if __name__ == "__main__":
    sys.exit(main())
