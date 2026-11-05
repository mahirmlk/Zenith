"""Hybrid retrieval: BM25 (stdlib) + pgvector, fused (update.md §8.3).

Deterministic BM25 over title+abstract for keyword recall; vector
similarity via Supabase `match_papers` when available. Results are
never mixed across project scopes at the router layer.
"""
import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def bm25_scores(query: str, docs: list[dict], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """BM25 score per doc (docs have title+abstract)."""
    q = tokenize(query)
    if not q or not docs:
        return [0.0] * len(docs)
    doc_tokens = [tokenize(f"{d.get('title','')} {d.get('abstract','')}") for d in docs]
    avgdl = sum(len(t) for t in doc_tokens) / max(len(doc_tokens), 1)
    df = Counter()
    for toks in doc_tokens:
        df.update(set(toks))
    n = len(docs)
    scores = []
    for toks in doc_tokens:
        tf = Counter(toks)
        dl = len(toks) or 1
        score = 0.0
        for term in set(q):
            f = tf.get(term, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        scores.append(score)
    return scores


def hybrid_fuse(bm25: list[float], vector: list[float], alpha: float = 0.5) -> list[float]:
    """Min-max normalize each side, then weighted fuse."""
    def _norm(xs: list[float]) -> list[float]:
        lo, hi = min(xs, default=0.0), max(xs, default=0.0)
        span = hi - lo
        return [(x - lo) / span if span else 0.0 for x in xs]

    b, v = _norm(bm25), _norm(vector)
    return [alpha * x + (1 - alpha) * y for x, y in zip(b, v)]


def hybrid_rank(query: str, docs: list[dict], vector_scores: list[float] | None = None) -> list[dict]:
    """Return docs with `score` attached, sorted descending."""
    bm25 = bm25_scores(query, docs)
    vector = vector_scores if vector_scores is not None else [0.0] * len(docs)
    fused = hybrid_fuse(bm25, vector)
    ranked = [{**d, "score": s} for d, s in zip(docs, fused)]
    return sorted(ranked, key=lambda d: d["score"], reverse=True)
