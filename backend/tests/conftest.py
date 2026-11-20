import pytest
from main import app
from tests.asgi_client import ASGITestClient

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def client() -> ASGITestClient:
    return ASGITestClient(app)


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
