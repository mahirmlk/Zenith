"""Hybrid retrieval + evidence tests (update.md §8). Offline/deterministic."""
from services.evidence_store import Claim, EvidenceItem, validate_evidence
from services.retrieval import bm25_scores, hybrid_fuse, hybrid_rank

DOCS = [
    {"id": "a", "title": "Diffusion models for images", "abstract": "We study diffusion sampling."},
    {"id": "b", "title": "Graph neural networks", "abstract": "Message passing on graphs."},
    {"id": "c", "title": "Diffusion sampling theory", "abstract": "Diffusion theory and proofs."},
]


def test_bm25_relevant_doc_wins():
    scores = bm25_scores("diffusion sampling", DOCS)
    assert scores[0] > scores[1]
    assert scores[0] > 0


def test_bm25_empty_query():
    assert bm25_scores("", DOCS) == [0.0, 0.0, 0.0]


def test_hybrid_rank_orders_and_scores():
    ranked = hybrid_rank("diffusion", DOCS)
    assert ranked[0]["id"] in ("a", "c")
    assert ranked[0]["score"] >= ranked[-1]["score"]
    fused = hybrid_fuse([0.0, 1.0], [1.0, 0.0])
    assert fused == [0.5, 0.5]


def test_evidence_validation():
    good = [Claim(claim_text="x", evidence=[EvidenceItem(paper_id="a")])]
    assert validate_evidence(good, {"a"}) == []
    bad = [Claim(claim_text="y", evidence=[EvidenceItem(paper_id="fake")])]
    assert validate_evidence(bad, {"a"}) != []
