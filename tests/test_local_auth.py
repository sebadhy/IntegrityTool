"""Passwords and sessions use only isolated fixtures, never real credentials."""
import hashlib
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.analyzer.review_store import ReviewStore
from src.local_auth import COOKIE, LocalAuth, hash_password, sessions, users, verify_password

PASSWORD = "fixture-not-a-default-43!"
ORIGIN = "https://integrity.test:8443"


@pytest.fixture
def auth(tmp_path):
    store = ReviewStore(tmp_path / "auth.sqlite3")
    auth = LocalAuth(store.engine, initialize=True)
    auth.add_user("admin.test", "Administrador", "admin", PASSWORD, first_admin=True)
    yield auth
    store.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key, value in {"INTEGRITY_WEB_MODE": "password", "INTEGRITY_PUBLIC_ORIGIN": ORIGIN,
            "INTEGRITY_ACCESS_POLICY": "shared_team", "INTEGRITY_WORKER_MODE": "external"}.items():
        monkeypatch.setenv(key, value)
    path = tmp_path / "api.sqlite3"
    store = ReviewStore(path)
    local = LocalAuth(store.engine, initialize=True)
    local.add_user("admin.test", "Administrador", "admin", PASSWORD, first_admin=True)
    local.add_user("reader.test", "Consulta", "reader", PASSWORD)
    store.close()
    from src.workbench_api import create_app
    with TestClient(create_app(path, assisted=False), base_url=ORIGIN) as test:
        test.headers["Origin"] = ORIGIN
        yield test


def test_scrypt_is_salted_and_password_not_stored():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong-password-123", first)
    with pytest.raises(ValueError):
        hash_password("short")


def test_no_default_accounts_or_second_bootstrap(auth):
    with pytest.raises(ValueError):
        auth.add_user("another.admin", "Otro", "admin", PASSWORD, first_admin=True)
    with auth.engine.connect() as db:
        assert len(list(db.execute(select(users)))) == 1


def test_only_session_digest_is_stored_and_logout_revokes(auth):
    token, _ = auth.login("ADMIN.TEST", PASSWORD)
    headers = {"cookie": f"{COOKIE}={token}"}
    assert auth.authenticate(headers).actor.startswith("local:")
    with auth.engine.connect() as db:
        row = db.execute(select(sessions)).mappings().one()
        assert row["digest"] == hashlib.sha256(token.encode()).hexdigest()
        assert token not in json.dumps(dict(row))
    auth.logout(headers)
    with pytest.raises(HTTPException) as error:
        auth.authenticate(headers)
    assert error.value.status_code == 401


def test_throttle_survives_auth_instance_restart(auth):
    for _ in range(5):
        with pytest.raises(HTTPException) as error:
            auth.login("admin.test", "incorrect-pass-123")
        assert error.value.status_code == 401
    restarted = LocalAuth(auth.engine)
    with pytest.raises(HTTPException) as error:
        restarted.login("admin.test", PASSWORD)
    assert error.value.status_code == 429
    restarted.change_user("admin.test", unlock=True)
    assert restarted.login("admin.test", PASSWORD)


@pytest.mark.parametrize("seconds", [1801, 8 * 3600 + 1])
def test_idle_and_absolute_expiration(auth, monkeypatch, seconds):
    token, _ = auth.login("admin.test", PASSWORD)
    import time
    future = time.time() + seconds
    monkeypatch.setattr("src.local_auth.time.time", lambda: future)
    with pytest.raises(HTTPException):
        auth.authenticate({"cookie": f"{COOKIE}={token}"})


def test_reset_password_and_disable_revoke_active_sessions(auth):
    auth.add_user("reviewer.test", "Revisión", "reviewer", PASSWORD)
    token, _ = auth.login("reviewer.test", PASSWORD)
    auth.change_user("reviewer.test", password="changed-fixture-pass-123")
    with pytest.raises(HTTPException):
        auth.authenticate({"cookie": f"{COOKIE}={token}"})
    token, _ = auth.login("reviewer.test", "changed-fixture-pass-123")
    auth.change_user("reviewer.test", disable=True)
    with pytest.raises(HTTPException):
        auth.authenticate({"cookie": f"{COOKIE}={token}"})
    with pytest.raises(ValueError):
        auth.change_user("admin.test", disable=True)


def test_password_routes_csrf_cookie_and_revocation(client):
    assert client.get("/api/auth/config").json() == {"mode": "password"}
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/cases/not-a-case/documents/not-a-doc").status_code == 401
    payload = {"username": "admin.test", "password": PASSWORD}
    assert client.post("/api/auth/login", json=payload, headers={"Origin": "https://other.test"}).status_code == 403
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for expected in ("Secure", "HttpOnly", "SameSite=strict", "Path=/", "__Host-"):
        assert expected in cookie
    assert client.get("/api/session").json()["can_write"]
    assert client.get("/api/cases").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/cases").status_code == 401


def test_reader_cannot_write_but_can_logout(client):
    assert client.post("/api/auth/login", json={"username": "reader.test", "password": PASSWORD}).status_code == 200
    assert not client.get("/api/session").json()["can_write"]
    for method, path in (("POST", "/api/cases"), ("POST", "/api/cases/x/retry"), ("PUT", "/api/cases/x/items/y/review")):
        assert client.request(method, path).status_code == 403
    assert client.post("/api/auth/logout").status_code == 200


def test_login_http_throttle_has_retry_header(client):
    for _ in range(5):
        response = client.post("/api/auth/login", json={"username": "admin.test", "password": "incorrect-fixture-password"})
        assert response.status_code == 401
    response = client.post("/api/auth/login", json={"username": "admin.test", "password": PASSWORD})
    assert response.status_code == 429 and response.headers["retry-after"] == "900"


def test_validation_does_not_echo_password(client):
    secret = "private-input-" * 30
    response = client.post("/api/auth/login", json={"username": "admin.test", "password": secret})
    assert response.status_code == 422 and secret not in response.text


def test_login_rejects_oversized_body_before_validation(client):
    secret = "do-not-echo" * 1000
    response = client.post("/api/auth/login", json={"username": "admin.test", "password": secret})
    assert response.status_code == 413 and secret not in response.text


def test_unsigned_identity_cannot_replace_local_cookie(client):
    assert client.get("/api/cases", headers={"X-MS-CLIENT-PRINCIPAL": "admin", "X-Forwarded-User": "admin.test"}).status_code == 401


def test_missing_auth_schema_fails_closed(tmp_path):
    store = ReviewStore(tmp_path / "empty.sqlite3")
    try:
        with pytest.raises(ValueError, match="init-admin"):
            LocalAuth(store.engine)
    finally:
        store.close()


def test_invalid_username_never_aliases_a_real_account(auth):
    auth.add_user("invalid-username", "Cuenta válida", "reader", PASSWORD)
    with pytest.raises(HTTPException):
        auth.login("!!!", PASSWORD)
