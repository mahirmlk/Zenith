"""
Seed script for local development.
Populates the Supabase DB with sample papers so the frontend has data to display.

Run: python -m backend.scripts.seed_dev
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import get_settings
from backend.services.embeddings import embed_texts
from supabase import create_client


SAMPLE_PAPERS = [
    {
        "id": "arxiv-2401.001",
        "title": "Attention Is All You Need: A Survey of Transformer Variants",
        "abstract": "We survey the landscape of transformer architectures developed since the original 'Attention Is All You Need' paper, analyzing efficiency improvements and novel attention mechanisms.",
        "authors": ["Alice Smith", "Bob Jones"],
        "url": "https://arxiv.org/pdf/2401.001.pdf",
        "published_at": "2024-01-15T00:00:00+00:00",
    },
    {
        "id": "arxiv-2401.002",
        "title": "Diffusion Models for Text-to-Image Synthesis: A Comprehensive Review",
        "abstract": "This paper provides a comprehensive review of diffusion-based generative models for text-to-image synthesis, covering architectural innovations, training techniques, and evaluation metrics.",
        "authors": ["Carol White", "David Brown"],
        "url": "https://arxiv.org/pdf/2401.002.pdf",
        "published_at": "2024-01-20T00:00:00+00:00",
    },
    {
        "id": "arxiv-2401.003",
        "title": "Reinforcement Learning from Human Feedback: Methods and Applications",
        "abstract": "We examine methods for aligning large language models with human preferences through reinforcement learning, discussing PPO, DPO, and emerging alternatives.",
        "authors": ["Eve Green", "Frank Black"],
        "url": "https://arxiv.org/pdf/2401.003.pdf",
        "published_at": "2024-02-01T00:00:00+00:00",
    },
    {
        "id": "arxiv-2401.004",
        "title": "Scaling Laws for Neural Language Models in Low-Resource Settings",
        "abstract": "An empirical study of how transformer language models scale when trained on limited data, with practical recommendations for model size and training duration.",
        "authors": ["Grace Lee", "Henry Wilson"],
        "url": "https://arxiv.org/pdf/2401.004.pdf",
        "published_at": "2024-02-10T00:00:00+00:00",
    },
    {
        "id": "arxiv-2401.005",
        "title": "Multimodal Foundation Models: Bridging Vision and Language",
        "abstract": "We propose a unified framework for multimodal understanding that integrates vision encoders with large language models through novel cross-modal attention mechanisms.",
        "authors": ["Ivy Chen", "Jack Taylor"],
        "url": "https://arxiv.org/pdf/2401.005.pdf",
        "published_at": "2024-02-15T00:00:00+00:00",
    },
]


async def main():
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    print("Checking for existing papers...")
    existing = await supabase.table("papers").select("id").execute()
    existing_ids = {r["id"] for r in existing.data or []}

    new_papers = [p for p in SAMPLE_PAPERS if p["id"] not in existing_ids]
    if not new_papers:
        print("All sample papers already exist. Nothing to seed.")
        return

    print(f"Seeding {len(new_papers)} sample papers...")

    texts = [f"{p['title']}\n{p['abstract']}" for p in new_papers]
    try:
        embeddings = await embed_texts(texts)
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        print("Seeding without embeddings...")
        embeddings = [None] * len(new_papers)

    rows = []
    for p, emb in zip(new_papers, embeddings):
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "abstract": p["abstract"],
            "authors": p["authors"],
            "url": p["url"],
            "published_at": p["published_at"],
            "embedding": emb,
            "summary_tldr": p["abstract"][:150] + "...",
            "difficulty": "intermediate",
        })

    await supabase.table("papers").upsert(rows).execute()
    print(f"Successfully seeded {len(rows)} papers.")


if __name__ == "__main__":
    asyncio.run(main())
