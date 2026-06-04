from typing import Callable, Awaitable
import re
import logging
from models.schemas import AgentStep
from services.mem0_client import get_user_profile
from services.embeddings import embed_texts

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "must", "can", "this", "that",
    "these", "those", "with", "from", "by", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "also", "its", "as", "we", "our", "us", "i",
    "me", "my", "mine", "he", "him", "his", "she", "her", "hers", "they", "them",
    "their", "theirs", "you", "your", "yours", "it",
}


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


async def _try_match_papers_sql(interest_text: str, papers: list[dict]) -> bool:
    """Try to use the match_papers SQL function for scoring. Returns True if successful."""
    try:
        from services.supabase_client import get_supabase
        from services.embeddings import embed_text

        interest_vec = await embed_text(interest_text)
        supabase = get_supabase()

        result = supabase.rpc(
            "match_papers",
            {
                "query_embedding": interest_vec,
                "match_threshold": 0.3,
                "match_count": len(papers),
            },
        ).execute()

        if result.data:
            scored_ids = {r["id"]: r["similarity"] for r in result.data}
            for paper in papers:
                paper["relevance_score"] = scored_ids.get(paper.get("id", ""), 0.0)
            return True
    except Exception as e:
        logger.debug("match_papers SQL unavailable, falling back to Python: %s", e)
    return False


async def memory_agent(
    papers: list[dict],
    user_id: str,
    query: str,
    callback: Callable[[AgentStep], Awaitable[None]],
) -> list[dict]:
    await callback(AgentStep(agent="memory", status="loading_profile"))

    try:
        profile = await get_user_profile(user_id)
    except Exception:
        profile = []

    interests = []
    for mem in profile:
        content = mem.get("memory", "")
        if content:
            interests.append(content)

    await callback(AgentStep(agent="memory", status="scoring_papers"))

    if interests:
        interest_text = " ".join(interests)

        # Try SQL-based scoring first (faster, uses pgvector)
        sql_success = await _try_match_papers_sql(interest_text, papers)
        if sql_success:
            await callback(AgentStep(agent="memory", status="ranking_complete", count=len(papers)))
            return sorted(papers, key=lambda p: p.get("relevance_score", 0), reverse=True)

        # Fallback to Python-based embedding similarity
        try:
            embeddings = await embed_texts([interest_text] + [p.get("abstract", "") for p in papers])
            interest_vec = embeddings[0]
            paper_vecs = embeddings[1:]

            def cosine_sim(a: list[float], b: list[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = sum(x * x for x in a) ** 0.5
                norm_b = sum(x * x for x in b) ** 0.5
                return dot / (norm_a * norm_b + 1e-10)

            for paper, vec in zip(papers, paper_vecs):
                paper["relevance_score"] = cosine_sim(interest_vec, vec)
        except Exception:
            for paper in papers:
                paper["relevance_score"] = 0.5
    else:
        query_keywords = _extract_keywords(query)
        if query_keywords:
            for paper in papers:
                text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
                paper_keywords = _extract_keywords(text)
                matches = len(query_keywords & paper_keywords)
                paper["relevance_score"] = min(1.0, matches / max(len(query_keywords), 1))
        else:
            for paper in papers:
                paper["relevance_score"] = 0.5

    await callback(AgentStep(agent="memory", status="ranking_complete", count=len(papers)))
    return sorted(papers, key=lambda p: p.get("relevance_score", 0), reverse=True)
