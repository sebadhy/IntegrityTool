import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from src.web_access import READ_ROLE, REVIEW_ROLE, WebAccess, web_configuration_errors
from src.workbench_api import create_app
from src.analyzer.review_worker import ReviewWorker
from test_workbench import pdf

TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"
ORIGIN = "https://integrity.example"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def entra(monkeypatch, signing_key):
    for key, value in {"INTEGRITY_WEB_MODE": "entra", "INTEGRITY_WORKER_MODE": "external",
        "INTEGRITY_ENTRA_TENANT_ID": TENANT, "INTEGRITY_ENTRA_CLIENT_ID": CLIENT,
        "INTEGRITY_PUBLIC_ORIGIN": ORIGIN, "INTEGRITY_ACCESS_POLICY": "shared_team"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt",
        lambda self, token: SimpleNamespace(key=signing_key.public_key()))


def token(signing_key, **overrides):
    now = int(time.time())
    claims = {"exp": now + 600, "iat": now - 10, "nbf": now - 10,
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT,
        "tid": TENANT, "oid": USER, "sub": "synthetic-user-subject", "nonce": "synthetic-login-nonce",
        "ver": "2.0", "name": "Revisor de prueba", "roles": [REVIEW_ROLE], **overrides}
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "synthetic-signing-key"})


@pytest.fixture
def client(entra, tmp_path):
    with TestClient(create_app(tmp_path / "secure.sqlite3", assisted=False,
            corpus_provider=lambda hashes: ({}, {"snapshot": "test", "total_processes": 0})),
            base_url=ORIGIN) as instance:
        yield instance


def headers(signing_key, **claims):
    return {"x-ms-token-aad-id-token": token(signing_key, **claims), "Origin": ORIGIN}


def test_anonymous_and_unsigned_principal_cannot_read_data(client):
    for path in ("/api/session", "/api/cases", "/api/cases/unknown", "/api/cases/unknown/documents/unknown",
                 "/api/cases/unknown/export", "/api/cases/unknown/history", "/api/cases/unknown/taxonomy"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"x-ms-client-principal": "forged", "x-ms-client-principal-id": USER}).status_code == 401


def test_liveness_is_minimal_and_does_not_expose_data(client):
    assert client.get("/healthz", headers={"Host": "internal-probe"}).json() == {"status": "ok"}
    assert client.head("/healthz").status_code == 200
    assert client.get("/api/health").status_code == 401


@pytest.mark.parametrize("overrides", [
    {"exp": 1}, {"nbf": 9999999999}, {"aud": "wrong-app"}, {"iss": "https://attacker.invalid/"},
    {"tid": "44444444-4444-4444-8444-444444444444"}, {"oid": "invalid"}, {"oid": 1},
    {"ver": "1.0"}, {"idtyp": "app"}, {"nonce": ""},
])
def test_invalid_signed_claims_are_rejected(client, signing_key, overrides):
    assert client.get("/api/session", headers=headers(signing_key, **overrides)).status_code == 401


def test_signature_and_algorithm_cannot_be_forged(client, signing_key):
    forged = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.get("/api/session", headers=headers(forged)).status_code == 401
    for bad in ("not-a-token", jwt.encode({"oid": USER}, "synthetic-secret-with-at-least-32-characters", algorithm="HS256")):
        assert client.get("/api/session", headers={"x-ms-token-aad-id-token": bad}).status_code == 401


def test_other_roles_and_unassigned_users_are_denied(client, signing_key):
    for roles in ([], ["GlobalAdministrator"], ["OtherApp.Reviewer"], "Integrity.Reviewer"):
        assert client.get("/api/cases", headers=headers(signing_key, roles=roles)).status_code == 403


def test_reader_is_read_only_for_all_mutations(client, signing_key):
    auth = headers(signing_key, roles=[READ_ROLE])
    assert client.get("/api/session", headers=auth).json()["can_write"] is False
    assert client.get("/api/cases", headers=auth).status_code == 200
    for method, path in (("POST", "/api/cases"), ("POST", "/api/sources/sercop/record"),
                         ("POST", "/api/cases/unknown/retry"), ("PUT", "/api/cases/unknown/items/unknown/review")):
        assert client.request(method, path, headers=auth).status_code == 403


def test_origin_host_and_forwarded_headers_cannot_bypass_policy(client, signing_key):
    auth = headers(signing_key)
    assert client.post("/api/cases", headers={**auth, "Origin": "https://attacker.invalid"}).status_code == 403
    assert client.post("/api/cases", headers={"x-ms-token-aad-id-token": token(signing_key)}).status_code == 403
    assert client.get("/api/cases", headers={**auth, "Host": "attacker.invalid", "X-Forwarded-Host": "integrity.example"}).status_code == 403
    assert client.get("/api/cases", headers={**auth, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/session", headers=auth).headers["cache-control"] == "no-store"


def test_verified_actor_is_used_and_reader_can_consult_shared_case(client, signing_key):
    auth = headers(signing_key)
    response = client.post("/api/cases", headers=auth,
        data={"manifest": '[{"role":"pliego"}]', "request_key": "entra-test"},
        files=[("files", ("pliego.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 202
    identity = response.json()["id"]
    assert ReviewWorker(client.app.state.service).run_once()
    case = client.get(f"/api/cases/{identity}", headers=auth).json()
    item = case["result"]["items"][0]["id"]
    saved = client.put(f"/api/cases/{identity}/items/{item}/review", headers=auth,
        json={"state": "followup", "comment": "Revisado", "reviewer": "spoofed admin", "expected_revision": 0})
    assert saved.status_code == 200
    assert saved.json()["reviewer"] == f"entra:{TENANT}:{USER}"
    reader = headers(signing_key, roles=[READ_ROLE], oid="55555555-5555-4555-8555-555555555555")
    for path in (f"/api/cases/{identity}", f"/api/cases/{identity}/documents/{case['documents'][0]['id']}",
                 f"/api/cases/{identity}/export", f"/api/cases/{identity}/taxonomy"):
        assert client.get(path, headers=reader).status_code == 200
        assert client.get(path).status_code == 401
    events = client.get(f"/api/cases/{identity}/history", headers=auth).json()
    assert {event["state"] for event in events} == {"created", "followup"}
    assert all(event["reviewer"] == f"entra:{TENANT}:{USER}" for event in events)


def test_signing_key_failure_is_closed_and_redacted(client, signing_key, monkeypatch):
    def fail(*args):
        raise jwt.PyJWKClientConnectionError("private error with token")
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt", fail)
    response = client.get("/api/session", headers=headers(signing_key))
    assert response.status_code == 503 and "private error" not in response.text


def test_retry_records_verified_actor(client, signing_key):
    auth = headers(signing_key)
    response = client.post("/api/cases", headers=auth,
        data={"manifest": '[{"role":"pliego"}]', "request_key": "retry-actor"},
        files=[("files", ("pliego.pdf", pdf(), "application/pdf"))])
    case_id = response.json()["id"]
    assert ReviewWorker(client.app.state.service).run_once()
    client.app.state.service.store.update_case(case_id, "failed", error="Synthetic failure")
    assert client.post(f"/api/cases/{case_id}/retry", headers=auth).status_code == 202
    events = client.get(f"/api/cases/{case_id}/history", headers=auth).json()
    assert events[0]["state"] == "retry" and events[0]["reviewer"] == f"entra:{TENANT}:{USER}"


@pytest.mark.parametrize("key,value", [("INTEGRITY_WEB_MODE", "public"), ("INTEGRITY_ENTRA_TENANT_ID", "common"),
    ("INTEGRITY_ENTRA_CLIENT_ID", ""), ("INTEGRITY_PUBLIC_ORIGIN", "http://example.org"),
    ("INTEGRITY_PUBLIC_ORIGIN", "https://*.example.org"), ("INTEGRITY_PUBLIC_ORIGIN", "https://example.org/path"),
    ("INTEGRITY_PUBLIC_ORIGIN", "https://example.org/"), ("INTEGRITY_PUBLIC_ORIGIN", "https://bad host"),
    ("INTEGRITY_ACCESS_POLICY", ""), ("INTEGRITY_WORKER_MODE", "embedded")])
def test_invalid_public_configuration_refuses_startup(entra, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    assert web_configuration_errors()
    with pytest.raises(ValueError):
        WebAccess()


def test_local_mode_rejects_remote_peer_even_with_local_host(monkeypatch, tmp_path):
    monkeypatch.setenv("INTEGRITY_WEB_MODE", "local")
    with TestClient(create_app(tmp_path / "local.sqlite3", assisted=False),
                    base_url="http://localhost", client=("192.0.2.1", 1234)) as remote:
        assert remote.get("/api/cases").status_code == 403
