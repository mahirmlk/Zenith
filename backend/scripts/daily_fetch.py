"""
Daily cron script to fetch new papers from ArXiv and HuggingFace.

Run locally from the repo root:  python -m backend.scripts.daily_fetch
Run inside the backend container: python -m scripts.daily_fetch
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    # Local dev: python -m backend.scripts.daily_fetch (from repo root)
    from backend.config import get_settings
    from backend.services.ingestion import run_daily_fetch
except ModuleNotFoundError:
    # Container: python -m scripts.daily_fetch (from /app where backend/ is the root)
    from config import get_settings
    from services.ingestion import run_daily_fetch


async def main() -> None:
    get_settings()
    result = await run_daily_fetch()
    print(f"Fetched={result['fetched']} inserted={result['inserted']} summarised={result['summarised']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
