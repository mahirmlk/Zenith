from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_binds_services_only_to_loopback() -> None:
    compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:3000:3000"' in compose
    assert '"127.0.0.1:8000:8000"' in compose


def test_frontend_waits_for_backend_readiness() -> None:
    compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    frontend = compose.split("\n  backend:\n", maxsplit=1)[0]

    assert "condition: service_healthy" in frontend
    assert "http://localhost:8000/api/ready" in compose
