"""Score deterministic watchlist matcher and notification-selection fixtures.

Provider fixtures model records already returned by Semantic Scholar; they do
not measure the live provider's relation precision or recall. Incomplete source
cases are reported separately and excluded from recall denominators.
Usage: python evals/runners/run_watchlist_evals.py
"""
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "watchlist_notifications_v1.jsonl"
sys.path.insert(0, str(ROOT / "backend"))

from services.ingestion import _watchlist_matches  # noqa: E402


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    candidates = case["candidates"]
    seen: set[str] = set()
    predicted: set[str] = set()
    contract_mismatches: list[str] = []
    duplicate_count = 0
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        if candidate_id in seen:
            duplicate_count += 1
            continue
        seen.add(candidate_id)
        if case["target_type"] == "topic":
            selected = _watchlist_matches(case["query"], candidate)
        else:
            selected = candidate.get("provider_selected") is True
        expected_selected = candidate.get("expected_selected")
        if expected_selected is not None and selected != expected_selected:
            contract_mismatches.append(candidate_id)
        if selected:
            predicted.add(candidate_id)

    important = {str(item["id"]) for item in candidates if item.get("important") is True}
    return {
        "id": case["id"],
        "target_type": case["target_type"],
        "source_complete": case["source_complete"],
        "predicted": predicted,
        "important": important,
        "true_positives": predicted & important,
        "false_positives": predicted - important,
        "missed_important": important - predicted,
        "duplicate_candidates": duplicate_count,
        "contract_mismatches": contract_mismatches,
    }


def main() -> int:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cases) < 5:
        print(f"FAIL watchlist_notifications_v1: expected at least 5 cases, found {len(cases)}")
        return 1

    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    failed = 0
    for case in cases:
        result = evaluate_case(case)
        if result["contract_mismatches"]:
            failed += 1
        status = "COMPLETE" if result["source_complete"] else "INCOMPLETE"
        if result["source_complete"]:
            bucket = totals[result["target_type"]]
            bucket["tp"] += len(result["true_positives"])
            bucket["fp"] += len(result["false_positives"])
            bucket["missed"] += len(result["missed_important"])
            bucket["important"] += len(result["important"])
            bucket["duplicates"] += result["duplicate_candidates"]
        print(
            f"{status} {result['id']} type={result['target_type']} "
            f"tp={len(result['true_positives'])} fp={len(result['false_positives'])} "
            f"missed={sorted(result['missed_important'])} "
            f"duplicates={result['duplicate_candidates']} "
            f"contract_mismatches={result['contract_mismatches']}"
        )

    for target_type, metrics in sorted(totals.items()):
        predicted_count = metrics["tp"] + metrics["fp"]
        precision = metrics["tp"] / predicted_count if predicted_count else 1.0
        recall = metrics["tp"] / metrics["important"] if metrics["important"] else 1.0
        print(
            f"METRIC {target_type} precision={precision:.3f} recall={recall:.3f} "
            f"false_positives={metrics['fp']} missed_important={metrics['missed']} "
            f"duplicate_candidates={metrics['duplicates']}"
        )
        # This small, hand-labeled contract corpus is a smoke gate, not a
        # production-quality target. Human-calibrated thresholds remain open.
        if precision < 0.5 or recall < 0.5:
            failed += 1

    incomplete = sum(not case["source_complete"] for case in cases)
    print(
        f"watchlist_notifications_v1: {len(cases)} cases, "
        f"{incomplete} incomplete source cases excluded from recall"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
