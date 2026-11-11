"""HTTPS acceptance with synthetic data; no provider calls unless enabled.

--exercise explicitly creates a technical review and comment. This script never
restarts services, changes users or deletes data. Credentials are not printed.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import secrets
import socket
import ssl
import time
from pathlib import Path
from urllib.parse import urlsplit


def fixture_pdf() -> bytes:
    content = b"BT /F1 11 Tf 72 720 Td (Debe ser distribuidor autorizado exclusivo del fabricante X.) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"]
    output, offsets = b"%PDF-1.4\n", [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output += str(index).encode() + b" 0 obj\n" + value + b"\nendobj\n"
    start = len(output)
    output += b"xref\n0 6\n0000000000 65535 f \n"
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return output + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


class Client:
    def __init__(self, origin, ca=None, connect_address=None):
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("Use un origen HTTPS exacto.")
        self.origin, self.parsed = origin, parsed
        self.context = ssl.create_default_context(cafile=str(ca) if ca else None)
        self.connect_address, self.cookie = connect_address, ""

    def request(self, path, method="GET", data=None, headers=None):
        connection = http.client.HTTPSConnection(self.parsed.hostname, self.parsed.port or 443, context=self.context, timeout=20)
        if self.connect_address:
            # Preserve TLS hostname verification and Host; override only routing.
            connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
                (self.connect_address, self.parsed.port or 443), timeout, source_address)
        request_headers = {"Host": self.parsed.netloc, "Origin": self.origin, **(headers or {})}
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        try:
            connection.request(method, path, body=data, headers=request_headers)
            response = connection.getresponse()
            body, status = response.read(), response.status
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.cookie = cookie.split(";", 1)[0]
            return status, body
        finally:
            connection.close()

    def json(self, path, method="GET", payload=None, expected=200):
        status, body = self.request(path, method, json.dumps(payload).encode() if payload is not None else None,
            {"Content-Type": "application/json"})
        if status != expected:
            raise AssertionError(f"{method} {path}: HTTP {status}, esperado {expected}.")
        return json.loads(body)

    def login(self, username, password):
        self.json("/api/auth/login", "POST", {"username": username, "password": password})
        return self.json("/api/session")

    def upload(self):
        pdf, boundary = fixture_pdf(), "integrity-" + secrets.token_hex(12)
        parts = []
        for name, value in (("manifest", '[{"role":"pliego"}]'), ("request_key", "installation-" + secrets.token_hex(12)),
                            ("title", "Prueba técnica de instalación")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="prueba-instalacion.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode() + pdf + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        status, body = self.request("/api/cases", "POST", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        assert status == 202, f"Carga: HTTP {status}."
        return json.loads(body)

    def wait_ready(self, case_id, seconds=180):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            case = self.json("/api/cases/" + case_id)
            if case["status"] == "ready":
                return case
            assert case["status"] in {"queued", "running"}, "El trabajo no finalizó correctamente."
            time.sleep(1)
        raise AssertionError("El trabajador no completó el trabajo dentro del plazo de prueba.")

    def validate_case(self, case_id):
        case = self.wait_ready(case_id)
        assert case["result"]["items"], "La prueba no produjo evidencia revisable."
        endpoint = "/api/cases/" + case_id
        doc = case["documents"][0]
        status, content = self.request(endpoint + "/documents/" + doc["id"])
        assert status == 200 and hashlib.sha256(content).hexdigest() == doc["sha256"]
        for kind in ("html", "csv", "json"):
            status, body = self.request(endpoint + "/export?format=" + kind)
            assert status == 200 and len(body) > 100
        return case


def main():
    parser = argparse.ArgumentParser(description="Verificar instalación HTTPS con un PDF ficticio opcional.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--ca", type=Path)
    parser.add_argument("--connect-address", help="Solo en laboratorio: IP sin cambiar Host ni validación TLS.")
    parser.add_argument("--username")
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--exercise", action="store_true", help="Crear revisión técnica y comentario; puede usar el proveedor si está habilitado.")
    parser.add_argument("--case-id", help="Comprobar un caso técnico existente después de reiniciar.")
    args = parser.parse_args()
    results = []
    try:
        client = Client(args.url, args.ca, args.connect_address)
        assert client.json("/healthz") == {"status": "ok"}
        assert client.json("/readyz") == {"status": "ok"}
        status, shell = client.request("/")
        assert status == 200 and b"Integrity" in shell
        assert client.request("/api/cases")[0] == 401
        assert client.request("/api/session", headers={"X-MS-CLIENT-PRINCIPAL": "forged"})[0] == 401
        results.append({"test": "https_and_anonymous_protection", "status": "PASS"})
        case_id = args.case_id
        if args.username:
            import getpass
            password = args.password_file.read_text().rstrip("\r\n") if args.password_file else getpass.getpass("Contraseña: ")
            session = client.login(args.username, password)
            del password
            assert session["mode"] == "password"
            results.append({"test": "login", "status": "PASS"})
            if args.exercise:
                assert session["can_write"], "Se requiere rol de revisión para la prueba funcional."
                case_id = client.upload()["id"]
                case = client.validate_case(case_id)
                item = case["result"]["items"][0]
                client.json(f"/api/cases/{case_id}/items/{item['id']}/review", "PUT", {
                    "state": "followup", "comment": "Comprobación técnica de instalación", "expected_revision": 0})
                results.append({"test": "pdf_worker_evidence_review_exports", "status": "PASS", "case_id": case_id})
            elif case_id:
                client.validate_case(case_id)
                results.append({"test": "existing_case_and_original", "status": "PASS", "case_id": case_id})
            client.json("/api/auth/logout", "POST")
            assert client.request("/api/cases")[0] == 401
            results.append({"test": "logout_revokes_session", "status": "PASS"})
        elif args.exercise or case_id:
            raise ValueError("Indique --username para comprobar revisiones.")
        else:
            results.append({"test": "login_and_functional_analysis", "status": "NOT TESTED"})
        print(json.dumps({"checks": results, "deployment_validated": False,
            "notice": "Complete persistencia, reinicio, restauración y aceptación en la VM asignada."}, ensure_ascii=False, indent=2))
    except Exception:
        print(json.dumps({"checks": results + [{"test": "installation", "status": "FAIL"}],
            "notice": "Compruebe URL, certificado, cuentas y estado de los servicios. No se imprimen secretos."}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
