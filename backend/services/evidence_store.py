"""Evidence model (update.md §8.4): claims linked to exact source spans.

Every externally verifiable answer exposes document/version, citation
anchor (page/section/chunk), and claim→source relation. Fabricated
source IDs are rejected by `validate_evidence`.
"""
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    paper_id: str
    title: str = ""
    url: str = ""
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    chunk_index: int | None = None
    snippet: str = ""


class Claim(BaseModel):
    claim_text: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    relation: str = "not verified"  # supports | contradicts | mentions | not verified
    origin: str = "synthesis"  # paper_claim | synthesis | reproduced


def validate_evidence(claims: list[Claim], retrieved_ids: set[str]) -> list[str]:
    """Return claims citing sources outside the retrieved set (must be [])."""
    bad = []
    for claim in claims:
        for item in claim.evidence:
            if item.paper_id not in retrieved_ids:
                bad.append(f"{claim.claim_text[:40]} -> {item.paper_id}")
    return bad
