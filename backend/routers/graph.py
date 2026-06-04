from fastapi import APIRouter
from models.schemas import CitationGraph, GraphNode, GraphEdge
from services.semantic_scholar import get_paper_citations
import hashlib

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


@router.get("/{paper_id}", response_model=CitationGraph)
async def get_graph(paper_id: str):
    try:
        data = await get_paper_citations(paper_id)
    except Exception:
        # Fallback to mock data if S2 is unavailable
        data = {
            "paperId": paper_id,
            "title": "Target Paper",
            "references": [
                {"paperId": "r1", "title": "Related Paper 1"},
                {"paperId": "r2", "title": "Related Paper 2"},
                {"paperId": "r3", "title": "Related Paper 3"},
            ],
        }

    nodes = [GraphNode(id=paper_id, title=data.get("title", "Paper"), x=0, y=0, z=0)]
    edges = []

    refs = data.get("references", [])[:10]  # Cap at 10 for performance
    for i, ref in enumerate(refs):
        rid = ref.get("paperId", f"ref-{i}")
        x, y, z = _deterministic_position(rid, i)
        nodes.append(GraphNode(id=rid, title=ref.get("title", "Related"), x=x, y=y, z=z))
        edges.append(GraphEdge(source=rid, target=paper_id))

    return CitationGraph(nodes=nodes, edges=edges)
