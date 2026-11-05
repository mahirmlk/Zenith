"""Re-embed papers missing embeddings (update.md §8.3).

Usage: python -m scripts.backfill_embeddings [--limit 100]
Idempotent: only touches rows where embedding IS NULL.
"""
import asyncio
import sys

from services.embeddings import embed_texts
from services.supabase_client import get_supabase


async def main(limit: int = 100) -> int:
    supabase = get_supabase()
    resp = await supabase.table("papers").select("id,title,abstract").is_("embedding", "null").range(0, limit - 1).execute()
    rows = resp.data or []
    if not rows:
        print("Nothing to backfill.")
        return 0
    texts = [f"{r.get('title','')}\n{r.get('abstract','')}" for r in rows]
    vectors = await embed_texts(texts)
    for row, vec in zip(rows, vectors):
        await supabase.table("papers").update({
            "embedding": vec,
            "embedding_model": "text-embedding-3-small",
            "embedding_version": "v1",
        }).eq("id", row["id"]).execute()
    print(f"Backfilled {len(rows)} papers.")
    return len(rows)


if __name__ == "__main__":
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 100
    asyncio.run(main(limit))
