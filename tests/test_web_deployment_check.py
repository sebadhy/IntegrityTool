import io
from types import SimpleNamespace

import pytest

from deploy import check_web


@pytest.mark.parametrize("origin", ["http://example.org", "https://example.org/", "https://user:secret@example.org", "https://example.org?q=secret"])
def test_only_https_origin_is_accepted(origin):
    with pytest.raises(ValueError):
        check_web.check_web(origin)


def test_checks_are_read_only_without_credentials(monkeypatch):
    calls = []
    def open_request(request, timeout):
        calls.append(request)
        assert request.get_method() == "GET" and request.data is None
        path = request.full_url.removeprefix("https://example.org")
        body, status = (b'<title>Integrity Tool</title>', 200) if path == "/" else (
            (b'{"status":"ok"}', 200) if path == "/healthz" else (b'{}', 401))
        response = io.BytesIO(body)
        response.code = status
        return response
    monkeypatch.setattr(check_web, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    assert check_web.check_web("https://example.org")["ok"]
    assert len(calls) == 5


def test_misconfigured_public_api_fails_acceptance(monkeypatch):
    def open_request(*args, **kwargs):
        response = io.BytesIO(b'<title>Streamlit</title>')
        response.code = 200
        return response
    monkeypatch.setattr(check_web, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    assert not check_web.check_web("https://example.org")["ok"]
