"""Deterministic research plan previews and fixed-budget contracts."""
import pytest

from services.research_planner import build_research_plan


@pytest.mark.parametrize(
    ("query", "task_type"),
    [
        ("compare A versus B", "compare"),
        ("difference between RAG and dense retrieval", "compare"),
        ("how does the method work?", "explain"),
        ("literature review of retrieval systems", "deep_research"),
        ("new papers about deep learning", "feed"),
        ("comparatively, this model is faster", "feed"),
        ("deepening the model improves quality", "feed"),
    ],
)
def test_plan_classification_uses_word_boundaries(query, task_type):
    assert build_research_plan(query).task_type == task_type


def test_compare_intent_precedes_explain_and_deep_phrases():
    plan = build_research_plan("Explain and compare the state of the art for retrievers")

    assert plan.task_type == "compare"
    assert [step.step_id for step in plan.steps] == [
        "retrieve_sources",
        "extract_evidence",
        "compare_sources",
        "identify_gaps",
    ]


def test_deep_plan_is_deterministic_bounded_and_explicitly_non_executing():
    first = build_research_plan("survey recent retrieval research", source_scope="project")
    second = build_research_plan("survey recent retrieval research", source_scope="project")

    assert first.model_dump() == second.model_dump()
    assert first.source_scope == "project"
    assert first.max_tool_calls <= 6
    assert first.max_sources <= 10
    assert first.max_depth <= 2
    assert first.max_wall_clock_seconds <= 90
    assert first.max_model_calls == 0
    assert first.estimated_cost_usd is None
    assert first.cost_tracking_available is False
    assert first.execution_available is False
    assert first.limits_are_preview_only is True
    assert all(step.execution_state == "proposed" for step in first.steps)
    assert "draft_synthesis" not in {step.step_id for step in first.steps}


def test_synthesis_steps_appear_only_when_feature_is_enabled():
    plan = build_research_plan("deep survey of retrieval", synthesis_enabled=True)

    assert plan.synthesis_available is True
    assert plan.max_model_calls == 2
    assert plan.max_output_tokens == 1800
    assert {"draft_synthesis", "review_claims"}.issubset({step.step_id for step in plan.steps})
