"""Small shared-team authentication store, independent of any identity provider.

Passwords use salted scrypt; only session digests are persisted. Administration
is an explicit offline CLI operation, never an anonymous bootstrap endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import uuid
from http.cookies import CookieError, SimpleCookie

from fastapi import HTTPException
from sqlalchemy import (Boolean, Column, Float, ForeignKey, Integer, MetaData,
                        String, Table, delete, inspect, select, text)

COOKIE = "__Host-integrity_session"
metadata = MetaData()
users = Table("local_auth_users", metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(80), unique=True, nullable=False),
    Column("name", String(120), nullable=False),
    Column("password_hash", String(256), nullable=False),
    Column("role", String(20), nullable=False),
    Column("enabled", Boolean, nullable=False))
sessions = Table("local_auth_sessions", metadata,
    Column("digest", String(64), primary_key=True),
    Column("user_id", ForeignKey("local_auth_users.id"), nullable=False),
    Column("expires", Float, nullable=False), Column("last_seen", Float, nullable=False))
attempts = Table("local_auth_attempts", metadata,
    Column("key", String(64), primary_key=True),
    Column("started", Float, nullable=False), Column("count", Integer, nullable=False))
version = Table("local_auth_version", metadata, Column("version", Integer, primary_key=True))
ROLES = {"admin", "reviewer", "reader"}
SESSION_SECONDS = 8 * 3600
IDLE_SECONDS = 30 * 60
WINDOW_SECONDS = 15 * 60


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.@-]{2,79}", value):
        raise ValueError("El usuario debe tener entre 3 y 80 caracteres: letras, números, punto, @, guion o guion bajo.")
    return value


def hash_password(password: str) -> str:
    if not 15 <= len(password) <= 256:
        raise ValueError("La contraseña debe tener entre 15 y 256 caracteres.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return f"scrypt32768r8p3${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt32768r8p3" or not 15 <= len(password) <= 256:
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3,
                                maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_from_headers(headers) -> str:
    try:
        cookies = SimpleCookie(headers.get("cookie", ""))
        token = cookies[COOKIE].value if COOKIE in cookies else ""
    except CookieError:
        token = ""
    return token if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) else ""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class LocalAuth:
    def __init__(self, engine, *, initialize=False):
        self.engine = engine
        if initialize:
            with engine.begin() as db:
                self._lock(db)
                metadata.create_all(db)
                if not db.scalar(select(version.c.version)):
                    db.execute(version.insert().values(version=1))
        with engine.connect() as db:
            names = set(inspect(db).get_table_names())
            if not set(metadata.tables) <= names or list(db.execute(select(version.c.version)).scalars()) != [1]:
                raise ValueError("Inicialice el acceso local con python -m src.manage_users init-admin.")
        self.dummy_hash = hash_password(secrets.token_urlsafe(32))

    @staticmethod
    def _lock(db):
        if db.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(1852400172)"))

    def login(self, username: str, password: str) -> tuple[str, dict]:
        try:
            username = normalize_username(username)
        except ValueError:
            username = ""
        now = time.time()
        account_key, global_key = _digest("account:" + username), _digest("global")
        denied, limited, result = True, False, None
        # Serialize login checks across replicas. Expensive hashing is bounded by
        # this gate, including unknown names; failures commit before we respond.
        with self.engine.begin() as db:
            self._lock(db)
            db.execute(delete(attempts).where(attempts.c.started <= now - WINDOW_SECONDS))
            db.execute(delete(sessions).where((sessions.c.expires <= now) | (sessions.c.last_seen <= now - IDLE_SECONDS)))
            counters = {row["key"]: row for row in db.execute(select(attempts)).mappings()}
            limited = (counters.get(account_key, {}).get("count", 0) >= 5 or
                       counters.get(global_key, {}).get("count", 0) >= 100)
            if not limited:
                user = db.execute(select(users).where(users.c.username == username)).mappings().first()
                valid = verify_password(password, user["password_hash"] if user else self.dummy_hash)
                if user and user["enabled"] and valid:
                    token = secrets.token_urlsafe(32)
                    db.execute(sessions.insert().values(digest=_digest(token), user_id=user["id"],
                        expires=now + SESSION_SECONDS, last_seen=now))
                    db.execute(delete(attempts).where(attempts.c.key == account_key))
                    denied, result = False, (token, dict(user))
                else:
                    for key in (global_key, account_key):
                        if key in counters:
                            db.execute(attempts.update().where(attempts.c.key == key).values(count=counters[key]["count"] + 1))
                        else:
                            db.execute(attempts.insert().values(key=key, count=1, started=now))
        if limited:
            raise HTTPException(429, "Se alcanzó el límite de intentos. Intente nuevamente en 15 minutos.")
        if denied:
            raise HTTPException(401, "Usuario o contraseña incorrectos.")
        return result

    def authenticate(self, headers):
        from .web_access import Identity
        token, now = token_from_headers(headers), time.time()
        if token:
            with self.engine.begin() as db:
                row = db.execute(select(users, sessions.c.expires, sessions.c.last_seen).join(
                    sessions, sessions.c.user_id == users.c.id).where(sessions.c.digest == _digest(token),
                    sessions.c.expires > now, sessions.c.last_seen > now - IDLE_SECONDS,
                    users.c.enabled.is_(True))).mappings().first()
                if row:
                    db.execute(sessions.update().where(sessions.c.digest == _digest(token)).values(last_seen=now))
                    return Identity("local:" + row["id"], row["name"], row["role"] in {"admin", "reviewer"}, "password")
        raise HTTPException(401, "Inicie sesión con su cuenta autorizada.")

    def logout(self, headers):
        token = token_from_headers(headers)
        with self.engine.begin() as db:
            db.execute(delete(sessions).where(sessions.c.digest == _digest(token)))

    def add_user(self, username, name, role, password, *, first_admin=False):
        username = normalize_username(username)
        if role not in ROLES or not name.strip() or len(name) > 120:
            raise ValueError("Indique un nombre y un rol admin, reviewer o reader.")
        password_hash = hash_password(password)
        with self.engine.begin() as db:
            self._lock(db)
            if first_admin and (role != "admin" or db.scalar(select(users.c.id).limit(1))):
                raise ValueError("El administrador inicial ya existe. Use create para agregar usuarios.")
            if db.scalar(select(users.c.id).where(users.c.username == username)):
                raise ValueError("El nombre de usuario ya existe.")
            db.execute(users.insert().values(id=str(uuid.uuid4()), username=username, name=name.strip(),
                role=role, password_hash=password_hash, enabled=True))

    def change_user(self, username, *, password=None, disable=False, unlock=False):
        username = normalize_username(username)
        encoded = hash_password(password) if password is not None else None
        with self.engine.begin() as db:
            self._lock(db)
            row = db.execute(select(users).where(users.c.username == username)).mappings().first()
            if not row:
                raise ValueError("El usuario no existe.")
            if disable and row["role"] == "admin" and not db.scalar(select(users.c.id).where(
                    users.c.enabled.is_(True), users.c.role == "admin", users.c.id != row["id"])):
                raise ValueError("No se puede deshabilitar al último administrador.")
            if encoded or disable:
                values = {"password_hash": encoded} if encoded else {}
                if disable:
                    values["enabled"] = False
                db.execute(users.update().where(users.c.id == row["id"]).values(**values))
                db.execute(delete(sessions).where(sessions.c.user_id == row["id"]))
            if unlock:
                db.execute(delete(attempts).where(attempts.c.key == _digest("account:" + username)))
