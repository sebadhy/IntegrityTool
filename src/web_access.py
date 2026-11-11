"""Local access or signed Entra identity forwarded by Container Apps Easy Auth.

Unsigned principal headers never authenticate a request. This release implements
one explicitly shared team workspace per deployment, not per-case tenancy.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException

READ_ROLE = "Integrity.Reader"
REVIEW_ROLE = "Integrity.Reviewer"


def web_configuration_errors() -> list[str]:
    mode = os.getenv("INTEGRITY_WEB_MODE", "local")
    if mode == "local":
        return []
    if mode != "entra":
        return ["INTEGRITY_WEB_MODE debe ser local o entra."]
    errors = []
    for key in ("INTEGRITY_ENTRA_TENANT_ID", "INTEGRITY_ENTRA_CLIENT_ID"):
        try:
            if str(UUID(os.getenv(key, ""))) != os.getenv(key, ""):
                raise ValueError()
        except ValueError:
            errors.append(f"Configure {key} como UUID en minúsculas.")
    try:
        origin = urlsplit(os.getenv("INTEGRITY_PUBLIC_ORIGIN", ""))
        if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment or origin.port is not None
                or origin.hostname in {"localhost", "127.0.0.1", "::1"}
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", origin.hostname)
                or ".." in origin.hostname or origin.netloc != origin.netloc.lower()):
            raise ValueError()
    except ValueError:
        errors.append("INTEGRITY_PUBLIC_ORIGIN requiere un origen HTTPS exacto, sin ruta ni barra final.")
    if os.getenv("INTEGRITY_ACCESS_POLICY") != "shared_team":
        errors.append("Confirme INTEGRITY_ACCESS_POLICY=shared_team para el espacio compartido del equipo autorizado.")
    if os.getenv("INTEGRITY_WORKER_MODE") != "external":
        errors.append("El acceso Entra requiere INTEGRITY_WORKER_MODE=external.")
    return errors


@dataclass(frozen=True)
class Identity:
    actor: str
    name: str
    can_write: bool
    mode: str


class WebAccess:
    def __init__(self):
        errors = web_configuration_errors()
        if errors:
            raise ValueError("\n".join(errors))
        self.mode = os.getenv("INTEGRITY_WEB_MODE", "local")
        self.origin = os.getenv("INTEGRITY_PUBLIC_ORIGIN", "") if self.mode == "entra" else ""
        self.tenant = os.getenv("INTEGRITY_ENTRA_TENANT_ID", "")
        self.client_id = os.getenv("INTEGRITY_ENTRA_CLIENT_ID", "")
        self.keys = None
        if self.mode == "entra":
            import jwt
            # Fixed authority derived from validated tenant ID; never from a token.
            self.keys = jwt.PyJWKClient(
                f"https://login.microsoftonline.com/{self.tenant}/discovery/v2.0/keys",
                cache_jwk_set=True, lifespan=300, timeout=5)

    def check_request(self, request):
        if self.mode == "local":
            if (request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}
                    or not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}):
                raise HTTPException(403, "Esta versión está habilitada solo para acceso local.")
        elif request.headers.get("host") != urlsplit(self.origin).netloc:
            raise HTTPException(403, "Dominio no autorizado.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if self.mode == "entra":
                if origin != self.origin:
                    raise HTTPException(403, "Origen de solicitud no autorizado.")
            elif origin and urlsplit(origin).netloc != request.headers.get("host"):
                raise HTTPException(403, "Origen de solicitud no autorizado.")
        if self.mode == "entra" and request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Solicitud entre sitios no autorizada.")

    def authenticate(self, headers) -> Identity:
        if self.mode == "local":
            return Identity("Revisor local", "Revisor local", True, "local")
        # Easy Auth token store supplies this signed ID token after OIDC login.
        # X-MS-CLIENT-PRINCIPAL and its identity/role headers are deliberately ignored.
        token = headers.get("x-ms-token-aad-id-token", "")
        if not token or len(token) > 24000:
            raise HTTPException(401, "Inicie sesión con su cuenta institucional.")
        import jwt
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or not 1 <= len(header["kid"]) <= 200:
                raise jwt.InvalidTokenError()
            key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"],
                audience=self.client_id, issuer=f"https://login.microsoftonline.com/{self.tenant}/v2.0",
                leeway=30, options={"require": ["exp", "iat", "nbf", "iss", "aud", "tid", "oid", "sub", "nonce"]})
            if (claims["tid"] != self.tenant or claims.get("ver") != "2.0" or claims.get("idtyp") == "app"
                    or not isinstance(claims["sub"], str) or not claims["sub"]
                    or not isinstance(claims["nonce"], str) or not claims["nonce"]
                    or not isinstance(claims["oid"], str)
                    or str(UUID(claims["oid"])) != claims["oid"]):
                raise jwt.InvalidTokenError()
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(503, "No se pudo verificar la sesión institucional. Intente nuevamente.") from None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise HTTPException(401, "La sesión institucional no es válida o venció. Inicie sesión nuevamente.") from None
        roles = claims.get("roles", [])
        if not isinstance(roles, list) or not any(role in roles for role in (READ_ROLE, REVIEW_ROLE)):
            raise HTTPException(403, "Su cuenta no tiene un rol autorizado para este espacio.")
        name = claims.get("name")
        return Identity(f"entra:{self.tenant}:{claims['oid']}",
            name[:120] if isinstance(name, str) and name.strip() else "Usuario institucional",
            REVIEW_ROLE in roles, "entra")
