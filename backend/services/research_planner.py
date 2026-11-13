"""Deterministic, provider-free previews of bounded research workflows."""
from agents.research_types import (
    ResearchPlan,
    ResearchPlanScope,
    ResearchPlanStep,
    ResearchPlanStepId,
    classify_task,
)


def build_research_plan(
    query: str,
    *,
    source_scope: ResearchPlanScope = "public_corpus",
    synthesis_enabled: bool = False,
) -> ResearchPlan:
    """Build a static preview; no sources, providers, or tools are accessed.

    Displayed limits are planning guidance only. Existing research routes enforce
    their own independent caps; there is no multi-step plan executor yet.
    """
    if source_scope not in {"public_corpus", "project"}:
        raise ValueError("Unsupported research source scope")

    task_type = classify_task(query).task_type
    templates: dict[str, tuple[list[tuple[ResearchPlanStepId, str, str]], int, int, int, int]] = {
        "feed": (
            [
                ("retrieve_sources", "Find candidate papers", "Rank matching paper metadata."),
                ("extract_evidence", "Select source evidence", "Select exact abstract sentences for relevant candidates."),
            ],
            2, 10, 20, 1,
        ),
        "explain": (
            [
                ("retrieve_sources", "Find relevant papers", "Rank matching paper metadata."),
                ("extract_evidence", "Collect exact evidence", "Select matching abstract sentences and eligible project page spans."),
            ],
            3, 10, 30, 1,
        ),
        "compare": (
            [
                ("retrieve_sources", "Find comparison sources", "Rank matching paper metadata within the selected scope."),
                ("compare_sources", "Extract comparison fields", "Match available abstract sentences to comparison dimensions."),
                ("identify_gaps", "Surface missing evidence", "Leave unsupported fields blank and keep PDF evidence separate."),
            ],
            4, 10, 45, 1,
        ),
        "deep_research": (
            [
                ("retrieve_sources", "Retrieve candidate sources", "Collect bounded source candidates in the selected scope."),
                ("extract_evidence", "Extract exact evidence", "Select source sentences with stable citations and offsets."),
                ("identify_gaps", "Inspect unanswered parts", "Identify which parts of the question lack matching source evidence."),
            ],
            6, 10, 90, 2,
        ),
    }
    raw_steps, max_tool_calls, max_sources, max_seconds, max_depth = templates[task_type]
    max_model_calls = 0
    max_output_tokens = 0
    if task_type == "deep_research":
        if synthesis_enabled:
            raw_steps.extend([
                ("draft_synthesis", "Draft provisional claims", "Use at most six exact public abstract sentences."),
                ("review_claims", "Review evidence relations", "Label support, conflict, or uncertainty; this is not independent verification."),
            ])
            max_model_calls = 2
            max_output_tokens = 1800
        else:
            raw_steps.append(
                ("synthesis_unavailable", "Synthesis is disabled", "Enable only after human review and staging quality gates pass.")
            )

    return ResearchPlan(
        query=query,
        task_type=task_type,
        max_tool_calls=max_tool_calls,
        max_sources=max_sources,
        source_scope=source_scope,
        steps=[ResearchPlanStep(step_id=step_id, title=title, description=description) for step_id, title, description in raw_steps],
        max_depth=max_depth,
        max_wall_clock_seconds=max_seconds,
        max_model_calls=max_model_calls,
        max_output_tokens=max_output_tokens,
        synthesis_available=synthesis_enabled,
        estimated_cost_usd=None,
        cost_tracking_available=False,
        execution_available=False,
        limits_are_preview_only=True,
    )
