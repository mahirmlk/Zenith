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


def test_production_compose_requires_essential_frontend_and_runtime_settings() -> None:
    compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    for variable in (
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "APP_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "REDIS_URL",
        "DATABASE_URL",
    ):
        assert f"${{{variable}:?" in compose


def test_ci_docker_build_inherits_compose_interpolation_placeholders() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    docker_job = workflow.split("  docker:\n", maxsplit=1)[1]
    job_header, _, steps = docker_job.partition("    steps:\n")

    assert "    env:\n" in job_header
    for variable in (
        "APP_URL",
        "DATABASE_URL",
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_URL",
        "REDIS_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_URL",
    ):
        assert f"      {variable}:" in job_header
    assert "docker compose -f docker-compose.prod.yml build" in steps
