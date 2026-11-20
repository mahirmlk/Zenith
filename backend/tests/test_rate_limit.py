from fastapi import APIRouter, FastAPI

from middleware import rate_limit


def test_project_pdf_upload_uses_a_low_upload_rate(monkeypatch):
    app = FastAPI()

    @app.post("/api/projects/{project_id}/documents")
    async def upload():
        return {"ok": True}

    applied: list[str] = []

    def capture_limit(rule: str):
        applied.append(rule)
        return lambda endpoint: endpoint

    monkeypatch.setattr(rate_limit.limiter, "limit", capture_limit)

    rate_limit.apply_rate_limits(app)

    assert applied == ["3/minute"]


def test_included_router_brief_mutations_are_rate_limited(monkeypatch):
    app = FastAPI()
    router = APIRouter(prefix="/api/projects/{project_id}/briefs")

    @router.post("")
    async def create_brief(request):
        return {"ok": True}

    @router.post("/{brief_id}/versions")
    async def append_brief_version(request):
        return {"ok": True}

    app.include_router(router)
    applied: list[str] = []

    def capture_limit(rule: str):
        applied.append(rule)
        return lambda endpoint: endpoint

    monkeypatch.setattr(rate_limit.limiter, "limit", capture_limit)
    rate_limit.apply_rate_limits(app)

    assert applied == ["20/minute", "20/minute"]
