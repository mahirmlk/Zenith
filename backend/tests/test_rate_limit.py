from fastapi import FastAPI

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
