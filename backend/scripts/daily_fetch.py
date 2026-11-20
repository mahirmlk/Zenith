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
    from backend.services.daily_scheduler import run_daily_fetch_with_lease
except ModuleNotFoundError:
    # Container: python -m scripts.daily_fetch (from /app where backend/ is the root)
    from config import get_settings
    from services.daily_scheduler import run_daily_fetch_with_lease


async def main() -> None:
    get_settings()
    lease_result = await run_daily_fetch_with_lease("fly-cron")
    if not lease_result.acquired:
        print("Skipped: another ingestion run owns the shared lease")
        return
    result = lease_result.result
    if not isinstance(result, dict):
        raise RuntimeError("Daily ingestion returned an invalid result")
    print(f"Fetched={result['fetched']} inserted={result['inserted']} summarised={result['summarised']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
