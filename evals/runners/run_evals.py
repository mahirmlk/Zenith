"""Evaluate deterministic retrieval, abstention, citation, and support.

This hermetic gate calls the same hybrid ranker and extractive claim selector
as the API. It does not assess broad scientific correctness or deployed state.
Usage: python evals/runners/run_evals.py
"""
import json
import pathlib
import re
import sys
import asyncio
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "grounded_qa_v3.jsonl"
DATASET_VERSION = "grounded_qa_v3"
PDF_DATASET = ROOT / "evals" / "datasets" / "pdf_evidence_v1.jsonl"
PDF_DATASET_VERSION = "pdf_evidence_v1"
SYNTHESIS_DATASET = ROOT / "evals" / "datasets" / "cross_paper_synthesis_v1.jsonl"
SYNTHESIS_DATASET_VERSION = "cross_paper_synthesis_v1"
PLAN_DATASET = ROOT / "evals" / "datasets" / "research_plan_v1.jsonl"
PLAN_DATASET_VERSION = "research_plan_v1"
TOP_K = 5
sys.path.insert(0, str(ROOT / "backend"))

from routers.research import _extractive_claims, _extractive_pdf_evidence  # noqa: E402
from security.output_validation import validate_citations  # noqa: E402
from services.retrieval import hybrid_rank  # noqa: E402
from services import synthesis  # noqa: E402
from agents.research_types import SynthesisEvidenceItem  # noqa: E402
from services.research_planner import build_research_plan  # noqa: E402


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


def evaluate_pdf_case(case: dict) -> dict:
    evidence = _extractive_pdf_evidence(
        case["query"],
        case.get("documents", []),
        case.get("pages", []),
        limit=5,
    )
    expected = case["expected"]
    citations = [item.citation_id for item in evidence]
    snippets = [item.sentence for item in evidence]
    page_text = {
        (str(page.get("document_id")), page.get("page_number")): page.get("text")
        for page in case.get("pages", [])
    }
    exact_spans = all(
        isinstance(page_text.get((item.document_id, item.page_number)), str)
        and page_text[(item.document_id, item.page_number)][item.start_offset:item.end_offset]
        == item.sentence
        for item in evidence
    )
    forbidden_phrases = [phrase.casefold() for phrase in expected.get("forbidden_phrases", [])]
    forbidden_absent = not any(
        phrase in sentence.casefold()
        for phrase in forbidden_phrases
        for sentence in snippets
    )
    checks = {
        "citation_ids": citations == expected.get("citation_ids", []),
        "exact_snippets": snippets == expected.get("snippets", []),
        "exact_page_spans": exact_spans,
        "abstention": (not evidence) == expected.get("must_abstain", False),
        "forbidden_text_absent": forbidden_absent,
    }
    return {
        "id": case["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "citations": citations,
        "snippets": snippets,
    }


async def evaluate_synthesis_case(case: dict) -> dict:
    class FixtureLLM:
        def __init__(self, responses: list[str]) -> None:
            self.responses = list(responses)

        async def ainvoke(self, _messages):
            return SimpleNamespace(content=self.responses.pop(0))

    evidence = [SynthesisEvidenceItem.model_validate(item) for item in case["evidence"]]
    llm = FixtureLLM(case["provider_responses"])
    original_get_llm = synthesis.get_llm
    synthesis.get_llm = lambda **_kwargs: llm
    try:
        try:
            claims = await synthesis.synthesize_claims(case["query"], evidence)
            invalid_output_rejected = False
        except synthesis.SynthesisOutputError:
            claims = []
            invalid_output_rejected = True
    finally:
        synthesis.get_llm = original_get_llm

    expected = case["expected"]
    statuses = [claim.status for claim in claims]
    allowed_ids = {item.evidence_id for item in evidence}
    citations_valid = all(
        evidence_id in allowed_ids
        for claim in claims
        for evidence_id in claim.cited_evidence_ids
    )
    checks = {
        "statuses": statuses == expected.get("statuses", []),
        "citations_valid": citations_valid,
        "invalid_output_rejected": invalid_output_rejected == expected.get("reject_invalid", False),
        "provider_calls_bounded": len(case["provider_responses"]) - len(llm.responses) <= 2,
    }
    return {"id": case["id"], "passed": all(checks.values()), "checks": checks, "statuses": statuses}


def evaluate_plan_case(case: dict) -> dict:
    plan = build_research_plan(
        case["query"],
        source_scope=case["scope"],
        synthesis_enabled=case["synthesis_enabled"],
    )
    expected = case["expected"]
    step_ids = [step.step_id for step in plan.steps]
    checks = {
        "task_type": plan.task_type == expected["task_type"],
        "ordered_steps": step_ids == expected["steps"],
        "budgets_bounded": (
            0 <= plan.max_depth <= 2
            and 0 <= plan.max_tool_calls <= 6
            and 0 <= plan.max_sources <= 10
            and 0 <= plan.max_wall_clock_seconds <= 90
            and 0 <= plan.max_model_calls <= 2
            and 0 <= plan.max_output_tokens <= 1800
        ),
        "preview_only": not plan.execution_available and plan.limits_are_preview_only,
        "cost_not_fabricated": plan.estimated_cost_usd is None and not plan.cost_tracking_available,
        "steps_not_executed": all(step.execution_state == "proposed" for step in plan.steps),
    }
    return {"id": case["id"], "passed": all(checks.values()), "checks": checks, "steps": step_ids}


def main() -> int:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    pdf_cases = [
        json.loads(line)
        for line in PDF_DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    synthesis_cases = [
        json.loads(line)
        for line in SYNTHESIS_DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    plan_cases = [
        json.loads(line)
        for line in PLAN_DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(cases) < 10:
        print(f"FAIL {DATASET_VERSION}: expected at least 10 cases, found {len(cases)}")
        return 1
    if len(pdf_cases) < 5:
        print(f"FAIL {PDF_DATASET_VERSION}: expected at least 5 cases, found {len(pdf_cases)}")
        return 1
    if len(synthesis_cases) < 3:
        print(f"FAIL {SYNTHESIS_DATASET_VERSION}: expected at least 3 cases, found {len(synthesis_cases)}")
        return 1
    if len(plan_cases) < 5:
        print(f"FAIL {PLAN_DATASET_VERSION}: expected at least 5 cases, found {len(plan_cases)}")
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

    pdf_results = []
    for case in pdf_cases:
        result = evaluate_pdf_case(case)
        pdf_results.append(result)
        failed_checks = [name for name, passed in result["checks"].items() if not passed]
        label = "PASS" if result["passed"] else "FAIL"
        print(
            f"{label} {result['id']} pdf_citations={result['citations']}"
            + (f" failed={','.join(failed_checks)}" if failed_checks else "")
        )

    synthesis_results = []
    for case in synthesis_cases:
        result = asyncio.run(evaluate_synthesis_case(case))
        synthesis_results.append(result)
        failed_checks = [name for name, passed in result["checks"].items() if not passed]
        label = "PASS" if result["passed"] else "FAIL"
        print(
            f"{label} {result['id']} synthesis_statuses={result['statuses']}"
            + (f" failed={','.join(failed_checks)}" if failed_checks else "")
        )

    plan_results = []
    for case in plan_cases:
        result = evaluate_plan_case(case)
        plan_results.append(result)
        failed_checks = [name for name, passed in result["checks"].items() if not passed]
        label = "PASS" if result["passed"] else "FAIL"
        print(
            f"{label} {result['id']} plan_steps={result['steps']}"
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
    pdf_failures = sum(not result["passed"] for result in pdf_results)
    synthesis_failures = sum(not result["passed"] for result in synthesis_results)
    plan_failures = sum(not result["passed"] for result in plan_results)
    failed_metrics = [name for name, value in metrics.items() if value < thresholds[name]]
    if failed_metrics:
        print(f"FAILED METRIC GATES: {', '.join(failed_metrics)}")
    print(
        f"{DATASET_VERSION}: {len(results)} cases, "
        f"{len(results) - failures} passed, {failures} failed; "
        f"fabricated_citation_control={'PASS' if fabricated_rejected else 'FAIL'}"
    )
    pdf_metrics = {
        "pdf_citation_accuracy": sum(result["checks"]["citation_ids"] for result in pdf_results) / len(pdf_results),
        "pdf_exact_span_rate": sum(result["checks"]["exact_page_spans"] for result in pdf_results) / len(pdf_results),
        "pdf_abstention_accuracy": sum(result["checks"]["abstention"] for result in pdf_results) / len(pdf_results),
        "pdf_forbidden_text_safety": sum(result["checks"]["forbidden_text_absent"] for result in pdf_results) / len(pdf_results),
    }
    for name, value in pdf_metrics.items():
        print(f"METRIC {name}={value:.3f} threshold=1.000")
    pdf_failed_metrics = [name for name, value in pdf_metrics.items() if value < 1.0]
    if pdf_failed_metrics:
        print(f"FAILED {PDF_DATASET_VERSION} METRIC GATES: {', '.join(pdf_failed_metrics)}")
    print(
        f"{PDF_DATASET_VERSION}: {len(pdf_results)} cases, "
        f"{len(pdf_results) - pdf_failures} passed, {pdf_failures} failed"
    )
    print(
        f"{SYNTHESIS_DATASET_VERSION}: {len(synthesis_results)} cases, "
        f"{len(synthesis_results) - synthesis_failures} passed, {synthesis_failures} failed"
    )
    print(
        f"{PLAN_DATASET_VERSION}: {len(plan_results)} cases, "
        f"{len(plan_results) - plan_failures} passed, {plan_failures} failed"
    )
    return 1 if failures or failed_metrics or pdf_failures or pdf_failed_metrics or synthesis_failures or plan_failures or not fabricated_rejected else 0


if __name__ == "__main__":
    sys.exit(main())
