"""Deterministic tests for bounded synthesis anchors and verifier outcomes."""
import json
from types import SimpleNamespace

import pytest

from agents.research_types import SynthesisEvidenceItem
from services import synthesis


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.messages = []

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return SimpleNamespace(content=self.responses.pop(0))


def _evidence() -> list[SynthesisEvidenceItem]:
    return [
        SynthesisEvidenceItem(
            evidence_id="E1",
            paper_id="paper-a",
            title="Study A",
            sentence="Diffusion retrieval increased recall in the Harbor benchmark.",
            start_offset=4,
            end_offset=65,
        ),
        SynthesisEvidenceItem(
            evidence_id="E2",
            paper_id="paper-b",
            title="Study B",
            sentence="Diffusion retrieval decreased recall in the Redwood benchmark.",
            start_offset=9,
            end_offset=71,
        ),
    ]


@pytest.mark.asyncio
async def test_synthesis_returns_conflict_with_only_verified_evidence_ids(monkeypatch):
    llm = FakeLLM([
        json.dumps({"claims": [{"text": "The papers report different recall outcomes.", "evidence_ids": ["E1", "E2"]}]}),
        json.dumps({"assessments": [{
            "claim_index": 0,
            "status": "conflicting",
            "supporting_evidence_ids": ["E1"],
            "contradicting_evidence_ids": ["E2"],
            "explanation": "The two exact sentences report opposite directions.",
        }]}),
    ])
    monkeypatch.setattr(synthesis, "get_llm", lambda **_kwargs: llm)

    claims = await synthesis.synthesize_claims("diffusion retrieval recall", _evidence())

    assert len(claims) == 1
    assert claims[0].status == "conflicting"
    assert claims[0].supporting_evidence_ids == ["E1"]
    assert claims[0].contradicting_evidence_ids == ["E2"]
    assert claims[0].cited_evidence_ids == ["E1", "E2"]
    assert all("private PDF" not in str(message.content) for call in llm.messages for message in call)


@pytest.mark.asyncio
async def test_synthesis_rejects_fabricated_evidence_ids_before_verification(monkeypatch):
    llm = FakeLLM([
        json.dumps({"claims": [{"text": "A fabricated result.", "evidence_ids": ["E1", "missing"]}]}),
    ])
    monkeypatch.setattr(synthesis, "get_llm", lambda **_kwargs: llm)

    with pytest.raises(synthesis.SynthesisOutputError, match="invalid citation"):
        await synthesis.synthesize_claims("diffusion retrieval recall", _evidence())

    assert len(llm.messages) == 1


@pytest.mark.asyncio
async def test_synthesis_requires_two_distinct_papers_before_provider_call(monkeypatch):
    def no_provider_call(**_kwargs):
        raise AssertionError("provider should not be initialized")

    monkeypatch.setattr(synthesis, "get_llm", no_provider_call)
    evidence = [_evidence()[0], _evidence()[0].model_copy(update={"evidence_id": "E2"})]

    claims = await synthesis.synthesize_claims("diffusion retrieval recall", evidence)

    assert claims == []


@pytest.mark.asyncio
async def test_synthesis_rejects_evidence_marked_as_both_support_and_contradiction(monkeypatch):
    llm = FakeLLM([
        json.dumps({"claims": [{"text": "The papers report different recall outcomes.", "evidence_ids": ["E1", "E2"]}]}),
        json.dumps({"assessments": [{
            "claim_index": 0,
            "status": "conflicting",
            "supporting_evidence_ids": ["E1"],
            "contradicting_evidence_ids": ["E1", "E2"],
        }]}),
    ])
    monkeypatch.setattr(synthesis, "get_llm", lambda **_kwargs: llm)

    with pytest.raises(synthesis.SynthesisOutputError, match="invalid citation"):
        await synthesis.synthesize_claims("diffusion retrieval recall", _evidence())
