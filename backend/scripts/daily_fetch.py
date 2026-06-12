"""
Daily cron script to fetch new papers from ArXiv and HuggingFace.
Run via: python -m backend.scripts.daily_fetch
"""
import asyncio
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.arxiv import fetch_latest_papers
from backend.services.huggingface import fetch_hf_daily
from backend.services.embeddings import embed_texts
from backend.agents.summary_agent import summary_agent
from backend.models.schemas import AgentStep
from backend.config import get_settings
from supabase import create_client


async def main():
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    print("Fetching ArXiv papers...")
    arxiv_papers = await fetch_latest_papers(max_results=200)
    print(f"Found {len(arxiv_papers)} ArXiv papers")

    print("Fetching HuggingFace daily papers...")
    try:
        hf_papers = await fetch_hf_daily()
    except Exception as e:
        print(f"HF fetch failed: {e}")
        hf_papers = []
    print(f"Found {len(hf_papers)} HF papers")

    all_papers = {p["id"]: p for p in arxiv_papers + hf_papers}
    papers = list(all_papers.values())

    # Deduplicate against existing DB
    existing = await supabase.table("papers").select("id").execute()
    existing_ids = {r["id"] for r in existing.data or []}
    new_papers = [p for p in papers if p["id"] not in existing_ids]
    print(f"{len(new_papers)} new papers to insert")

    if not new_papers:
        return

    # Generate embeddings
    texts = [f"{p['title']}\n{p['abstract']}" for p in new_papers]
    try:
        embeddings = await embed_texts(texts)
    except Exception as e:
        print(f"Embedding failed: {e}")
        embeddings = [None] * len(new_papers)

    rows = []
    for p, emb in zip(new_papers, embeddings):
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "abstract": p["abstract"],
            "authors": p.get("authors", []),
            "url": p.get("url", ""),
            "published_at": p.get("published_at"),
            "embedding": emb,
        })

    # Batch insert
    for i in range(0, len(rows), 100):
        batch = rows[i:i+100]
        await supabase.table("papers").upsert(batch).execute()
        print(f"Inserted batch {i//100 + 1}")

    # Run summary agent on new papers
    print("Generating summaries...")
    try:
        async def _noop_cb(step: AgentStep):
            pass

        batch_size = 5
        for i in range(0, len(new_papers), batch_size):
            batch = new_papers[i:i+batch_size]
            paper_dicts = [
                {"id": p["id"], "title": p["title"], "abstract": p["abstract"]}
                for p in batch
            ]
            enriched = await summary_agent(paper_dicts, _noop_cb)
            for paper in enriched:
                await supabase.table("papers").update({
                    "summary_tldr": paper.get("summary_tldr"),
                    "difficulty": paper.get("difficulty", "intermediate"),
                }).eq("id", paper["id"]).execute()
            print(f"Summarised batch {i//batch_size + 1}/{ (len(new_papers) + batch_size - 1)//batch_size }")
            if i + batch_size < len(new_papers):
                await asyncio.sleep(2)
    except Exception as e:
        print(f"Summary generation failed: {e}")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
