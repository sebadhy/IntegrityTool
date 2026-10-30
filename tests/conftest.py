import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def block_external_http_transports(monkeypatch):
    """A local .env must never turn a unit test into a paid provider call.

    TestClient uses its own in-process ASGI transport. Provider tests must mock
    the SDK or transport explicitly; neither real HTTP transport is allowed.
    """
    def blocked(*args, **kwargs):
        raise AssertionError("External HTTP is disabled in tests; mock the provider.")

    async def blocked_async(*args, **kwargs):
        raise AssertionError("External HTTP is disabled in tests; mock the provider.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async)
