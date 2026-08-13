import re
from typing import Any

from fastapi import APIRouter, HTTPException
from models.schemas import CitationGraph, GraphNode, GraphEdge
from services.semantic_scholar import get_paper_citations
from services.citation_cache import get_cached_citations, store_citations
import hashlib

_PAPER_ID_RE = re.compile(r"^[a-zA-Z0-9\-._:/]+$")


def _validate_paper_id(paper_id: str) -> str:
    if not paper_id or len(paper_id) > 200:
        raise HTTPException(status_code=422, detail="Invalid paper ID format")
    if not _PAPER_ID_RE.match(paper_id):
        raise HTTPException(status_code=422, detail="Invalid paper ID format")
    return paper_id

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _deterministic_position(paper_id: str, index: int) -> tuple[float, float, float]:
    """Generate deterministic 3D position from paper ID and index."""
    hash_input = f"{paper_id}:{index}".encode()
    h = hashlib.sha256(hash_input).digest()
    # Convert first 12 bytes to 3 floats in range [-3, 3]
    x = (int.from_bytes(h[0:4], "big") / 0xFFFFFFFF) * 6 - 3
    y = (int.from_bytes(h[4:8], "big") / 0xFFFFFFFF) * 6 - 3
    z = (int.from_bytes(h[8:12], "big") / 0xFFFFFFFF) * 6 - 3
    return x, y, z


def _build_graph(paper_id: str, root_title: str, refs: list[dict[str, Any]]) -> CitationGraph:
    nodes = [GraphNode(id=paper_id, title=root_title, x=0, y=0, z=0)]
    edges = []
    for i, ref in enumerate(refs):
        rid = str(ref.get("paperId", f"ref-{i}"))
        x, y, z = _deterministic_position(rid, i)
        nodes.append(GraphNode(id=rid, title=str(ref.get("title", "Related")), x=x, y=y, z=z))
        edges.append(GraphEdge(source=rid, target=paper_id))
    return CitationGraph(nodes=nodes, edges=edges)


@router.get("/{paper_id}", response_model=CitationGraph)
async def get_graph(paper_id: str) -> CitationGraph:
    paper_id = _validate_paper_id(paper_id)

    # Serve from the Supabase cache first so the rate-limited S2 API is only
    # hit once per paper (refreshed when stale).
    cached = await get_cached_citations(paper_id)
    if cached is not None:
        refs = [
            {"paperId": r["cited_id"], "title": r["cited_title"]}
            for r in cached
        ]
        root_title = str(next((r.get("root_title") for r in cached if r.get("root_title")), "Paper"))
        return _build_graph(paper_id, root_title, refs)

    try:
        data = await get_paper_citations(paper_id)
    except Exception:
        return CitationGraph(nodes=[], edges=[])

    refs = data.get("references", [])[:10]  # Cap at 10 for performance
    root_title = str(data.get("title") or "Paper")
    await store_citations(paper_id, root_title, refs)
    return _build_graph(paper_id, root_title, refs)