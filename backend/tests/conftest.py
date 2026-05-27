import pytest
from fastapi.testclient import TestClient
from main import app

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
