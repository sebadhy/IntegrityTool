"""Public entry links must work without relaxing session or CSRF boundaries."""
import pytest
from fastapi.testclient import TestClient

from src.analyzer.review_store import ReviewStore
from src.local_auth import LocalAuth
from src.workbench_api import create_app
import src.workbench_api as web

ORIGIN = "https://integrity.example"
NAVIGATION = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate",
              "Sec-Fetch-Dest": "document", "Sec-Fetch-User": "?1"}


@pytest.fixture(params=["password", "entra"])
def public_client(request, monkeypatch, tmp_path):
    mode = request.param
    for key, value in {"INTEGRITY_WEB_MODE": mode, "INTEGRITY_WORKER_MODE": "external",
        "INTEGRITY_PUBLIC_ORIGIN": ORIGIN, "INTEGRITY_ACCESS_POLICY": "shared_team",
        "INTEGRITY_ENTRA_TENANT_ID": "11111111-1111-4111-8111-111111111111",
        "INTEGRITY_ENTRA_CLIENT_ID": "22222222-2222-4222-8222-222222222222"}.items():
        monkeypatch.setenv(key, value)
    # A tiny shell fixture makes this test independent of the frontend build.
    dist = tmp_path / "frontend/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>Public entry fixture</body></html>", encoding="utf-8")
    monkeypatch.setattr(web, "ROOT", tmp_path)
    storage = tmp_path / "navigation.sqlite3"
    if mode == "password":
        store = ReviewStore(storage)
        LocalAuth(store.engine, initialize=True)
        store.close()
    with TestClient(create_app(storage, assisted=False, corpus_provider=lambda hashes: ({}, {})), base_url=ORIGIN) as client:
        yield client


@pytest.mark.parametrize("referer", ["https://web.whatsapp.com/", "https://mail.google.com/",
    "https://outlook.office.com/", "https://teams.microsoft.com/", "https://app.slack.com/"])
def test_external_link_opens_only_public_shell(public_client, referer):
    response = public_client.get("/?revision=example", headers={**NAVIGATION, "Referer": referer})
    assert response.status_code == 200
    assert "Public entry fixture" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    # The landing page does not establish or bypass an authenticated session.
    assert public_client.get("/api/session").status_code == 401
    assert public_client.get("/api/cases").status_code == 401


def test_redirect_navigation_does_not_require_activation_header(public_client):
    headers = {key: value for key, value in NAVIGATION.items() if key != "Sec-Fetch-User"}
    assert public_client.get("/", headers=headers).status_code == 200


@pytest.mark.parametrize("mode,destination", [("cors", "empty"), ("no-cors", "image"),
    ("navigate", "iframe"), ("navigate", "frame"), ("", ""), ("navigate", "")])
def test_external_fetch_or_embedding_is_still_blocked(public_client, mode, destination):
    response = public_client.get("/", headers={**NAVIGATION, "Sec-Fetch-Mode": mode, "Sec-Fetch-Dest": destination})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/cases", "/api/session", "/api/auth/config",
    "/api/cases/example/export", "/api/cases/example/documents/example", "/assets/app.js"])
def test_navigation_exception_does_not_apply_to_data_or_assets(public_client, path):
    assert public_client.get(path, headers=NAVIGATION).status_code == 403


@pytest.mark.parametrize("method,path", [("POST", "/api/auth/login"), ("POST", "/api/cases"),
    ("PUT", "/api/cases/example/items/example/review"), ("DELETE", "/"), ("OPTIONS", "/")])
def test_external_mutations_remain_blocked_even_with_matching_origin(public_client, method, path):
    assert public_client.request(method, path, headers={**NAVIGATION, "Origin": ORIGIN}).status_code == 403


def test_host_origin_and_direct_entry_policy_are_preserved(public_client):
    assert public_client.get("/", headers={**NAVIGATION, "Host": "attacker.invalid"}).status_code == 403
    assert public_client.post("/api/cases", headers={"Origin": "https://attacker.invalid"}).status_code == 403
    assert public_client.post("/api/cases").status_code == 403
    assert public_client.get("/", headers={"Sec-Fetch-Site": "none"}).status_code == 200
    assert public_client.get("/", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
