from fastapi import APIRouter, HTTPException
from models.schemas import CitationGraph, GraphNode, GraphEdge
from services.semantic_scholar import get_paper_citations
import random

router = APIRouter(prefix="/api/graph", tags=["graph"])


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
        angle = (2 * 3.14159 * i) / max(len(refs), 1)
        radius = 3 + random.random()
        x = radius * (random.random() - 0.5) * 2
        y = radius * (random.random() - 0.5) * 2
        z = radius * (random.random() - 0.5) * 2
        nodes.append(GraphNode(id=rid, title=ref.get("title", "Related"), x=x, y=y, z=z))
        edges.append(GraphEdge(source=rid, target=paper_id))

    return CitationGraph(nodes=nodes, edges=edges)
