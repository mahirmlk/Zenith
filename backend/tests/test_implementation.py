"""Paper-to-code planner tests (update.md §11). Offline; no execution."""
from agents.implementation_planner import make_plan
from services.sandbox_runner import run_in_sandbox


def test_plan_generated_not_reproduced():
    plan = make_plan({"id": "p1", "abstract": "We propose X.", "summary_tldr": "X does Y"})
    assert plan.status == "plan generated"
    assert plan.citations == ["p1"]
    assert plan.checklist


def test_repos_marked_unverified():
    plan = make_plan({"id": "p1"}, repos=[{"url": "https://github.com/x/y", "stars": 3}])
    assert plan.candidate_repos[0]["verified"] is False


def test_sandbox_refuses_execution():
    result = run_in_sandbox(paper_id="p1")
    assert result["status"] == "not attempted"
