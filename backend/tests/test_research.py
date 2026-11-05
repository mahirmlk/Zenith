"""Deep-research routing/comparison tests (update.md §9). Offline."""
from agents.research_types import build_comparison, classify_task


def test_classify_compare():
    assert classify_task("compare diffusion vs GANs").task_type == "compare"


def test_classify_explain():
    assert classify_task("explain transformers").task_type == "explain"


def test_classify_deep():
    assert classify_task("deep survey of LLM agents").task_type == "deep_research"


def test_classify_feed_default():
    assert classify_task("new papers on diffusion").task_type == "feed"


def test_build_comparison_marks_code_unverified():
    rows = build_comparison([{"id": "p1", "title": "T", "abstract": "A"}])
    assert rows[0].paper_id == "p1"
    assert rows[0].code_status == "unverified"
