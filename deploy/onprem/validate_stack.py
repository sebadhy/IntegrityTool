"""Destructive acceptance ONLY in two newly created disposable Compose projects.

Never uses the developer's .env, documents, database or running demo. Requires
Docker Compose, OpenSSL and a prebuilt image. All fixtures are synthetic.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from verify_installation import Client

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description="Validar instalación, reinicio y restauración en proyectos descartables.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--port", type=int, default=18443)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnostics", type=Path, help="Guardar logs de los proyectos ficticios si falla la prueba (archivo protegido).")
    args = parser.parse_args()
    results, projects = [], []
    origin = f"https://integrity.test:{args.port}"
    success = False
    with tempfile.TemporaryDirectory(prefix="integrity-acceptance-") as directory:
        directory = Path(directory)
        private = directory / "secrets"
        subprocess.run([sys.executable, str(Path(__file__).with_name("prepare.py")), "--origin", origin,
                        "--directory", str(private)], check=True, capture_output=True)
        envfile = directory / "compose.env"
        envfile.write_text(f"INTEGRITY_PUBLIC_ORIGIN={origin}\nINTEGRITY_HTTPS_PORT={args.port}\n"
            f"INTEGRITY_BIND_ADDRESS=127.0.0.1\nINTEGRITY_SECRETS_DIR={private}\nINTEGRITY_IMAGE={args.image}\n")
        password = secrets.token_urlsafe(32)
        password_file = private / "acceptance_password"
        password_file.write_text(password)
        password_file.chmod(0o644)
        def compose(project, *arguments, data=None, timeout=180, allowed=(0,)):
            command = ["docker", "compose", "--env-file", str(envfile), "-p", project, "-f", str(ROOT / "compose.yaml"), *arguments]
            result = subprocess.run(command, cwd=ROOT, input=data, capture_output=True, timeout=timeout)
            if result.returncode not in allowed:
                # Commands never contain passwords. No stderr/body is emitted.
                raise RuntimeError("Falló Compose: " + " ".join(arguments[:6]))
            return result.stdout
        def wait_web(client):
            for _ in range(90):
                try:
                    if client.request("/readyz")[0] == 200:
                        return
                except (OSError, AssertionError):
                    pass
                time.sleep(1)
            raise AssertionError("El servicio no recuperó disponibilidad.")
        def client():
            return Client(origin, private / "web.crt", "127.0.0.1")
        def passed(name, **details):
            results.append({"test": name, "status": "PASS", **details})
        try:
            project = "integrity-validation-" + secrets.token_hex(4)
            projects.append(project)
            compose(project, "config", "--quiet")
            compose(project, "run", "--rm", "--no-deps", "storage-init")
            compose(project, "up", "-d", "--wait", "db")
            compose(project, "run", "--rm", "-T", "admin", "-m", "src.manage_storage", "init")
            user_args = ["run", "--rm", "-T", "-v", f"{password_file}:/run/acceptance-password:ro", "admin", "-m", "src.manage_users"]
            compose(project, *user_args, "init-admin", "acceptance.admin", "--password-file", "/run/acceptance-password")
            compose(project, *user_args, "create", "acceptance.reader", "--role", "reader", "--password-file", "/run/acceptance-password")
            compose(project, "up", "-d", "--wait", "api", "worker", "proxy")
            tls_check = "from src.runtime_secrets import load_secret_files; load_secret_files(); from src.analyzer.storage_settings import create_review_store; from pathlib import Path; from sqlalchemy import text,create_engine; s=create_review_store(Path('/app')); c=s.engine.connect(); assert c.execute(text('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()')).scalar(); c.close(); s.close()"
            compose(project, "run", "--rm", "-T", "admin", "-c", tls_check)
            c = client()
            wait_web(c)
            assert c.request("/api/cases")[0] == 401
            assert c.request("/api/session", headers={"X-MS-CLIENT-PRINCIPAL": "forged"})[0] == 401
            assert c.login("acceptance.admin", password)["can_write"]
            passed("clean_bootstrap_https_login_and_protection")
            case = c.upload()
            case = c.validate_case(case["id"])
            assert case["result"]["assistance"]["status"] == "disabled"
            item = case["result"]["items"][0]
            endpoint = f"/api/cases/{case['id']}/items/{item['id']}/review"
            c.json(endpoint, "PUT", {"state": "followup", "comment": "Aceptación técnica", "expected_revision": 0})
            assert c.json("/api/cases/" + case["id"])["reviews"][item["id"]]["reviewer"].startswith("local:")
            passed("pdf_upload_worker_analysis_evidence_audit_exports")
            reader = client()
            assert not reader.login("acceptance.reader", password)["can_write"]
            assert reader.request("/api/cases")[0] == 200
            assert reader.request(endpoint, "PUT", b"{}")[0] == 403
            reader.json("/api/auth/logout", "POST")
            assert reader.request("/api/cases")[0] == 401
            passed("reader_permissions_and_revocable_sessions")
            for _ in range(5):
                reader.json("/api/auth/login", "POST", {"username": "acceptance.reader", "password": "incorrect-fixture-password"}, expected=401)
            reader.json("/api/auth/login", "POST", {"username": "acceptance.reader", "password": password}, expected=429)
            compose(project, "restart", "api")
            wait_web(c)
            reader.json("/api/auth/login", "POST", {"username": "acceptance.reader", "password": password}, expected=429)
            compose(project, "run", "--rm", "-T", "admin", "-m", "src.manage_users", "unlock", "acceptance.reader")
            assert reader.login("acceptance.reader", password)
            passed("persistent_login_throttle_and_administrative_unlock")
            compose(project, "restart", "db", "api", "worker", "proxy")
            wait_web(c)
            c.validate_case(case["id"])
            passed("service_restart_preserves_session_documents_results")
            compose(project, "down", "--timeout", "30")
            compose(project, "up", "-d", "--wait", "db", "api", "worker", "proxy")
            wait_web(c)
            saved = c.validate_case(case["id"])
            assert saved["reviews"][item["id"]]["comment"] == "Aceptación técnica"
            passed("full_container_recreation_preserves_volumes_and_comments")
            compose(project, "stop", "worker")
            queued = c.upload()
            reserve = "from src.runtime_secrets import load_secret_files; load_secret_files(); from src.analyzer.storage_settings import create_review_store; from pathlib import Path; s=create_review_store(Path('/app')); lease=s.claim_job('acceptance-abandoned',lease_seconds=2); assert lease; s.close()"
            compose(project, "run", "--rm", "-T", "admin", "-c", reserve)
            time.sleep(3)
            compose(project, "up", "-d", "--wait", "worker")
            c.validate_case(queued["id"])
            passed("abandoned_worker_lease_recovery")
            # A fatal runtime filesystem error exits the real worker process.
            # Unlike `docker stop`, this does not suppress its restart policy.
            # Its tmpfs is fresh after restart; no persistent data is modified.
            compose(project, "exec", "-T", "worker", "python", "-c", "from pathlib import Path; Path('/tmp/worker-heartbeat').chmod(0)")
            container_id = compose(project, "ps", "-aq", "worker").decode().strip()
            for _ in range(30):
                restarted = subprocess.run(["docker", "inspect", "--format", "{{.RestartCount}}", container_id], capture_output=True, text=True, check=True)
                if int(restarted.stdout.strip()) >= 1:
                    break
                time.sleep(1)
            else:
                raise AssertionError("El motor no aplicó la política de reinicio del worker.")
            compose(project, "up", "-d", "--wait", "worker")
            c.validate_case(case["id"])
            passed("worker_failure_exit_automatic_restart_and_persisted_result")
            compose(project, "stop", "db")
            assert c.request("/readyz")[0] == 503
            compose(project, "up", "-d", "--wait", "db")
            wait_web(c)
            c.validate_case(case["id"])
            passed("database_outage_reconnect")
            # Consistent maintenance backup: stop all writers, retain DB service.
            compose(project, "stop", "api", "worker", "proxy")
            dump = compose(project, "exec", "-T", "db", "pg_dump", "-U", "postgres", "-d", "integrity", "-Fc")
            archive = compose(project, "run", "--rm", "-T", "--no-deps", "--entrypoint", "tar", "admin",
                "-C", "/var/lib/integrity/documents", "-czf", "-", ".")
            recovery = "integrity-validation-restore-" + secrets.token_hex(4)
            projects.append(recovery)
            compose(recovery, "run", "--rm", "--no-deps", "storage-init")
            compose(recovery, "up", "-d", "--wait", "db")
            compose(recovery, "exec", "-T", "db", "pg_restore", "-U", "postgres", "-d", "integrity", "--no-owner", "--role=integrity", data=dump)
            compose(recovery, "run", "--rm", "-T", "--no-deps", "--entrypoint", "tar", "admin",
                "-C", "/var/lib/integrity/documents", "-xzf", "-", data=archive)
            compose(recovery, "run", "--rm", "-T", "admin", "-m", "src.manage_users", "revoke-all")
            compose(recovery, "up", "-d", "--wait", "api", "worker", "proxy")
            recovered = client()
            wait_web(recovered)
            recovered.cookie = c.cookie
            assert recovered.request("/api/cases")[0] == 401
            recovered.cookie = ""
            recovered.login("acceptance.admin", password)
            restored = recovered.validate_case(case["id"])
            assert restored["reviews"][item["id"]]["comment"] == "Aceptación técnica"
            passed("backup_restore_into_new_database_and_document_volumes")
            success = True
        except Exception as exc:
            results.append({"test": "stack_acceptance", "status": "FAIL", "step": str(exc)[:180]})
            if args.diagnostics:
                with args.diagnostics.open("xb") as file:
                    os.chmod(args.diagnostics, 0o600)
                    for project in projects:
                        file.write(compose(project, "logs", "--no-color", "--tail", "60"))
        finally:
            for project in reversed(projects):
                try:
                    compose(project, "down", "--volumes", "--remove-orphans", "--timeout", "15")
                except Exception:
                    results.append({"test": "disposable_cleanup", "status": "FAIL", "project": project})
                    success = False
    results.extend({"test": name, "status": "NOT TESTED"} for name in (
        "physical_vm_reboot", "sercop_rhel_selinux", "podman", "azure_openai_authorized_live_credentials"))
    report = {"ok": success, "image": args.image, "checks": results,
        "scope": "Contenedores Linux sobre el motor disponible; no certifica la VM de destino.", "real_model_calls": 0}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8") as file:
            file.write(output + "\n")
    print(output)
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
