import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi import BackgroundTasks
from pydantic import BaseModel

from config import get_settings
from services.ingestion import run_daily_fetch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])


class IngestResponse(BaseModel):
    status: str


def _require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin endpoint not configured")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(_require_admin_key)])
async def trigger_daily_ingest(background_tasks: BackgroundTasks) -> IngestResponse:
    """Trigger the daily paper ingestion pipeline in the background.

    Intended for scheduled triggers (Fly scheduled machines or a GitHub
    Actions cron job). Requires the ``X-Admin-Key`` header to match
    ``ADMIN_API_KEY``.
    """
    background_tasks.add_task(run_daily_fetch)
    logger.info("Daily ingestion job queued")
    return IngestResponse(status="started")