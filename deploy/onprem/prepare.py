"""Generate installation-local secrets and lab certificates, never user accounts.

Requires Python 3 and OpenSSL on the administration host. Never overwrites an
existing directory; use institutional certificates before sharing the service.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description="Preparar secretos y certificados de laboratorio sin sobrescribir archivos.")
    parser.add_argument("--origin", required=True, help="Origen HTTPS exacto, por ejemplo https://integrity.example:8443")
    parser.add_argument("--directory", type=Path, default=Path(".secrets"))
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    if (origin.scheme != "https" or not origin.hostname or origin.path or origin.query or origin.fragment
            or origin.username or origin.password or origin.hostname in {"localhost", "127.0.0.1", "::1"}
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", origin.hostname)):
        parser.error("Use HTTPS con un nombre DNS o IP de pruebas, sin ruta ni barra final.")
    directory = args.directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(directory, 0o700)
    def write(name, value):
        path = directory / name
        path.write_text(value + "\n", encoding="utf-8")
        # File-backed secrets do not remap UID. Parent 0700 protects files on
        # the host; only explicitly mounted files are readable in containers.
        path.chmod(0o644)
    def openssl(*arguments):
        result = subprocess.run(["openssl", *map(str, arguments)], cwd=directory,
            capture_output=True, timeout=30)
        if result.returncode:
            raise SystemExit("No se generaron todos los certificados. Revise OpenSSL y el directorio antes de reintentar.")
    write("postgres_password", secrets.token_urlsafe(40))
    password = secrets.token_urlsafe(40)
    write("database_password", password)
    write("database_url", f"postgresql://integrity:{password}@db:5432/integrity?sslmode=verify-full&sslrootcert=/run/secrets/db_ca")
    openssl("req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "365", "-keyout", "db_ca.key",
        "-out", "db_ca.crt", "-subj", "/CN=Integrity installation database CA")
    openssl("req", "-newkey", "rsa:3072", "-nodes", "-keyout", "db_server.key", "-out", "db_server.csr", "-subj", "/CN=db")
    write("db_extensions", "subjectAltName=DNS:db\nextendedKeyUsage=serverAuth")
    openssl("x509", "-req", "-in", "db_server.csr", "-CA", "db_ca.crt", "-CAkey", "db_ca.key", "-CAcreateserial",
        "-out", "db_server.crt", "-days", "365", "-extfile", "db_extensions")
    try:
        ipaddress.ip_address(origin.hostname)
        san = "IP:" + origin.hostname
    except ValueError:
        san = "DNS:" + origin.hostname
    openssl("req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "30", "-keyout", "web.key",
        "-out", "web.crt", "-subj", "/CN=" + origin.hostname, "-addext", "subjectAltName=" + san)
    for name in ("web.key", "db_server.key", "web.crt", "db_ca.crt", "db_server.crt"):
        (directory / name).chmod(0o644)
    (directory / "db_ca.key").chmod(0o600)
    print("Secretos generados. No se crearon usuarios. El certificado web es de laboratorio (30 días); sustituirlo por uno institucional.")


if __name__ == "__main__":
    main()
