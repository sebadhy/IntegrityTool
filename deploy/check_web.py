"""Read-only acceptance checks against an HTTPS deployment; no user credentials."""
import argparse
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_web(origin: str) -> dict:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("Indique el origen HTTPS sin ruta, credenciales ni barra final.")
    opener = build_opener(NoRedirect())
    checks = []
    for name, path, headers in (
        ("frontend", "/", {}), ("liveness", "/healthz", {}),
        ("anonymous_cases_denied", "/api/cases", {}),
        ("anonymous_session_denied", "/api/session", {}),
        ("forged_identity_denied", "/api/cases", {"X-MS-CLIENT-PRINCIPAL": "forged", "X-MS-TOKEN-AAD-ID-TOKEN": "forged"}),
    ):
        try:
            try:
                response = opener.open(Request(origin + path, headers=headers), timeout=10)
            except HTTPError as error:
                response = error
            with response:
                status, body = response.code, response.read(1024 * 1024)
            if name == "frontend":
                valid = status == 200 and b"<title>Integrity Tool" in body and b"<title>Streamlit" not in body
            elif name == "liveness":
                valid = status == 200 and json.loads(body) == {"status": "ok"}
            else:
                valid = status in {401, 403}
            checks.append({"check": name, "ok": valid, "http_status": status})
        except Exception:
            checks.append({"check": name, "ok": False, "message": "No se pudo comprobar la respuesta esperada; revise TLS, ingreso y configuración."})
    return {"ok": all(entry["ok"] for entry in checks), "checks": checks,
            "notice": "Verificación anónima. Complete la aceptación con usuarios Reader y Reviewer y compruebe el commit autenticado."}


def main():
    parser = argparse.ArgumentParser(description="Verificar frontend, liveness y rechazo anónimo sin modificar datos.")
    parser.add_argument("origin")
    args = parser.parse_args()
    try:
        result = check_web(args.origin)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
