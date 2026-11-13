"""Bounded claim generation and model-based evidence relation review.

Only exact public paper abstract sentences are sent to providers. Project PDF
page text is never included in this workflow (see docs/security/DATA_HANDLING.md).
"""
import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.research_types import SynthesisClaim, SynthesisEvidenceItem
from services.llm_router import get_llm

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "agents" / "prompts"
_MAX_CLAIMS = 5
_MAX_EVIDENCE = 6
_MAX_SENTENCE_CHARS = 1200
_MAX_OUTPUT_TOKENS = 900
_CALL_TIMEOUT_SECONDS = 20


class SynthesisProviderError(RuntimeError):
    """The configured model provider failed or exceeded the bounded timeout."""


class SynthesisOutputError(RuntimeError):
    """A model response failed schema or citation-anchor validation."""


class _GeneratedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(min_length=2, max_length=_MAX_EVIDENCE)


class _GenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[_GeneratedClaim] = Field(max_length=_MAX_CLAIMS)


class _Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_index: int = Field(ge=0, lt=_MAX_CLAIMS)
    status: Literal["supported", "conflicting", "uncertain"]
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=_MAX_EVIDENCE)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=_MAX_EVIDENCE)
    explanation: str = Field(default="", max_length=500)


class _VerificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessments: list[_Assessment] = Field(max_length=_MAX_CLAIMS)


def _prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _parse_object(content: object, model: type[BaseModel]) -> BaseModel:
    if not isinstance(content, str) or len(content) > 20_000:
        raise SynthesisOutputError("Model returned an invalid response")
    try:
        payload = json.loads(content)
        return model.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise SynthesisOutputError("Model returned an invalid response") from exc


async def _invoke(messages: list[Any]) -> str:
    try:
        llm = get_llm(agent="summary_fast", temperature=0.0, max_tokens=_MAX_OUTPUT_TOKENS)
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=_CALL_TIMEOUT_SECONDS)
    except Exception as exc:
        raise SynthesisProviderError("Research synthesis provider unavailable") from exc
    content = getattr(response, "content", None)
    if not isinstance(content, str):
        raise SynthesisOutputError("Model returned an invalid response")
    return content


def _source_payload(evidence: list[SynthesisEvidenceItem]) -> list[dict[str, str]]:
    return [
        {
            "evidence_id": item.evidence_id,
            "paper_id": item.paper_id,
            "sentence": item.sentence,
        }
        for item in evidence
    ]


async def synthesize_claims(
    query: str,
    evidence: list[SynthesisEvidenceItem],
) -> list[SynthesisClaim]:
    """Synthesize at most five claims, then review support/conflict separately.

    Evidence IDs and exact quotes are created by the API before this function.
    Any unknown citation ID or malformed model response fails the whole request
    closed. A verifier assessment is model-reviewed, not independent proof.
    """
    bounded_evidence = [
        item for item in evidence[:_MAX_EVIDENCE]
        if len(item.sentence) <= _MAX_SENTENCE_CHARS
    ]
    if len({item.paper_id for item in bounded_evidence}) < 2:
        return []
    evidence_by_id = {item.evidence_id: item for item in bounded_evidence}
    generation_input = json.dumps(
        {"research_question": query[:500], "evidence": _source_payload(bounded_evidence)},
        ensure_ascii=False,
    )
    generation_content = await _invoke([
        SystemMessage(content=_prompt("cross_paper_synthesis.txt")),
        HumanMessage(content=generation_input),
    ])
    generated = _parse_object(generation_content, _GenerationOutput)
    if not isinstance(generated, _GenerationOutput):
        raise SynthesisOutputError("Model returned an invalid response")

    claims = generated.claims
    if not claims:
        return []
    for claim in claims:
        if len(set(claim.evidence_ids)) != len(claim.evidence_ids):
            raise SynthesisOutputError("Model returned an invalid response")
        selected = [evidence_by_id.get(evidence_id) for evidence_id in claim.evidence_ids]
        if any(item is None for item in selected):
            raise SynthesisOutputError("Model returned an invalid citation")
        if len({item.paper_id for item in selected if item is not None}) < 2:
            raise SynthesisOutputError("Model returned a single-source synthesis claim")

    verification_input = json.dumps(
        {
            "claims": [
                {"claim_index": index, "text": claim.text, "evidence_ids": claim.evidence_ids}
                for index, claim in enumerate(claims)
            ],
            "evidence": _source_payload(bounded_evidence),
        },
        ensure_ascii=False,
    )
    verification_content = await _invoke([
        SystemMessage(content=_prompt("claim_verification.txt")),
        HumanMessage(content=verification_input),
    ])
    verification = _parse_object(verification_content, _VerificationOutput)
    if not isinstance(verification, _VerificationOutput):
        raise SynthesisOutputError("Model returned an invalid response")

    assessments = {item.claim_index: item for item in verification.assessments}
    if len(assessments) != len(claims) or set(assessments) != set(range(len(claims))):
        raise SynthesisOutputError("Model returned incomplete claim assessments")

    results: list[SynthesisClaim] = []
    for index, claim in enumerate(claims):
        assessment = assessments[index]
        support_ids = assessment.supporting_evidence_ids
        contradiction_ids = assessment.contradicting_evidence_ids
        if (
            len(set(support_ids)) != len(support_ids)
            or len(set(contradiction_ids)) != len(contradiction_ids)
            or bool(set(support_ids).intersection(contradiction_ids))
            or not set(support_ids).issubset(evidence_by_id)
            or not set(contradiction_ids).issubset(evidence_by_id)
        ):
            raise SynthesisOutputError("Model returned an invalid citation")

        status = assessment.status
        support_papers = {evidence_by_id[evidence_id].paper_id for evidence_id in support_ids}
        contradiction_papers = {
            evidence_by_id[evidence_id].paper_id for evidence_id in contradiction_ids
        }
        independent_conflict = bool(
            support_papers
            and contradiction_papers
            and any(left != right for left in support_papers for right in contradiction_papers)
        )
        if status == "supported" and contradiction_ids:
            status = "conflicting" if independent_conflict else "uncertain"
        elif status == "supported" and len(support_papers) < 2:
            status = "uncertain"
        if status == "conflicting" and not independent_conflict:
            status = "uncertain"
        cited_ids = list(dict.fromkeys(support_ids + contradiction_ids))
        if not cited_ids:
            # Keep the generated claim visibly uncertain and link it to the
            # exact context it used; the UI must display its uncertain status.
            status = "uncertain"
            cited_ids = list(dict.fromkeys(claim.evidence_ids))
        results.append(
            SynthesisClaim(
                text=claim.text,
                status=status,
                supporting_evidence_ids=support_ids,
                contradicting_evidence_ids=contradiction_ids,
                cited_evidence_ids=cited_ids,
                explanation=assessment.explanation,
            )
        )
    return results
