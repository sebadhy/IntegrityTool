import sys
import importlib
import os
from pathlib import Path
from urllib.parse import urlparse

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

    for module_name in ("httpx", "httpx2"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        monkeypatch.setattr(module.HTTPTransport, "handle_request", blocked)
        monkeypatch.setattr(module.AsyncHTTPTransport, "handle_async_request", blocked_async)
    try:
        import requests
    except ImportError:
        return
    original_send = requests.Session.send
    def local_emulator_only(session, request, **kwargs):
        allowed = urlparse(os.getenv("INTEGRITY_TEST_AZURITE_URL", ""))
        actual = urlparse(request.url)
        if (allowed.hostname in {"localhost", "127.0.0.1", "::1"}
                and (actual.scheme, actual.hostname, actual.port) == (allowed.scheme, allowed.hostname, allowed.port)):
            return original_send(session, request, **kwargs)
        return blocked()
    monkeypatch.setattr(requests.Session, "send", local_emulator_only)
