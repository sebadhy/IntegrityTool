"""Smoke-test an already built image without Azure, credentials or model calls."""
import argparse
import json
import subprocess


def run(image, args, *, env=None, expected=0):
    command = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,size=128m", "--entrypoint", "python"]
    for key, value in (env or {}).items():
        command += ["--env", f"{key}={value}"]
    result = subprocess.run([*command, image, *args], capture_output=True, text=True, timeout=120)
    if result.returncode != expected:
        raise RuntimeError(f"Container check failed ({result.returncode}): {result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description="Validar imagen local sin conectividad externa.")
    parser.add_argument("image")
    image = parser.parse_args().image
    run(image, ["-c", "import os,shutil,subprocess,importlib.util; from pathlib import Path; "
        "assert os.geteuid()==10001; assert shutil.which('node') is None; "
        "assert Path('/app/frontend/dist/index.html').is_file(); "
        "assert Path('/app/installed-packages.txt').is_file(); "
        "assert not any(Path('/app').rglob('.env')); assert not Path('/app/.git').exists(); "
        "assert not Path('/app/data').exists(); "
        "assert importlib.util.find_spec('onnxruntime') is None; "
        "langs=subprocess.check_output(['tesseract','--list-langs'],text=True); "
        "assert 'spa' in langs.splitlines() and 'eng' in langs.splitlines()"])
    run(image, ["-m", "pip", "check"])
    missing = json.loads(run(image, ["-m", "src.deployment_check", "--role", "api"], expected=1))
    assert missing["ok"] is False and missing["model_calls"] == 0
    common = {
        "INTEGRITY_DATABASE_URL": "postgresql://test:test@not-a-real-server.invalid/db?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt",
        "INTEGRITY_DOCUMENT_STORAGE": "azure", "INTEGRITY_BLOB_CONTAINER": "integrity-test",
        "INTEGRITY_BLOB_ACCOUNT_URL": "https://not-a-real-account.invalid/",
        "INTEGRITY_WORKER_MODE": "external", "INTEGRITY_ASSISTED_ENABLED": "false",
    }
    for role in ("api", "worker"):
        checked = json.loads(run(image, ["-m", "src.deployment_check", "--role", role], env=common))
        assert checked["ok"] and checked["model_calls"] == 0 and checked["public_http_ready"] is False
    # Use only a temporary SQLite fixture, loopback HTTP and a disabled provider.
    # This tests the existing local API, not public/authenticated access in Azure.
    run(image, ["-c", '''
import hashlib, json, os, signal, sqlite3, subprocess, sys, time
import pymupdf
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
environment = dict(os.environ, INTEGRITY_STORE_PATH="/tmp/smoke/reviews.sqlite3",
    INTEGRITY_DOCUMENTS_PATH="/tmp/smoke/documents",
    INTEGRITY_DOCUMENT_STORAGE="filesystem", INTEGRITY_WORKER_MODE="external",
    INTEGRITY_ASSISTED_ENABLED="false")
process = subprocess.Popen([sys.executable,"-m","uvicorn","src.workbench_api:app",
    "--host","127.0.0.1","--port","8000"],env=environment)
try:
    for attempt in range(100):
        try:
            with urlopen("http://127.0.0.1:8000/api/health",timeout=2) as response:
                assert json.load(response)["status"]=="ok"
            break
        except URLError:
            if process.poll() is not None:
                raise AssertionError("Local API failed to start")
            time.sleep(.1)
    else:
        raise AssertionError("Local API startup timed out")
    with urlopen("http://127.0.0.1:8000/",timeout=5) as response:
        assert b"<html" in response.read()
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72,72), "Debe ser distribuidor autorizado exclusivo del fabricante X.")
    original = pdf.tobytes()
    pdf.close()
    boundary = "integrity-container-fixture"
    parts = []
    for name,value in (("manifest", '[{"role":"pliego"}]'), ("request_key", "container-fixture")):
        parts.append((f"--{boundary}\\r\\nContent-Disposition: form-data; name=\\\"{name}\\\"\\r\\n\\r\\n{value}\\r\\n").encode())
    parts.append((f"--{boundary}\\r\\nContent-Disposition: form-data; name=\\\"files\\\"; filename=\\\"pliego.pdf\\\"\\r\\nContent-Type: application/pdf\\r\\n\\r\\n").encode()+original+b"\\r\\n")
    parts.append(f"--{boundary}--\\r\\n".encode())
    request = Request("http://127.0.0.1:8000/api/cases",data=b"".join(parts),
        headers={"Content-Type":f"multipart/form-data; boundary={boundary}"},method="POST")
    with urlopen(request,timeout=10) as response:
        assert response.status==202
        case=json.load(response)
    subprocess.run([sys.executable,"-m","src.review_worker","--once"],env=environment,check=True,timeout=45)
    endpoint="http://127.0.0.1:8000/api/cases/"+case["id"]
    with urlopen(endpoint,timeout=5) as response:
        case=json.load(response)
        assert case["status"]=="ready" and case["result"]["items"]
        assert case["result"]["assistance"]["status"]=="disabled"
    document=case["documents"][0]
    with urlopen(endpoint+"/documents/"+document["id"],timeout=5) as response:
        assert hashlib.sha256(response.read()).hexdigest()==document["sha256"]
    item=case["result"]["items"][0]
    request=Request(endpoint+"/items/"+item["id"]+"/review",method="PUT",
        data=json.dumps({"state":"followup","comment":"Prueba local de contenedor","expected_revision":0}).encode(),
        headers={"Content-Type":"application/json"})
    with urlopen(request,timeout=5) as response:
        assert json.load(response)["revision"]==1
    for format in ("html","csv","json"):
        with urlopen(endpoint+"/export?format="+format,timeout=5) as response:
            assert len(response.read())>100
    with sqlite3.connect("/tmp/smoke/reviews.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM assisted_requests").fetchone()[0]==0
    try:
        urlopen(Request("http://127.0.0.1:8000/api/health",headers={"Host":"untrusted.example"}),timeout=5)
    except HTTPError as error:
        assert error.code==403
    else:
        raise AssertionError("Unknown host was accepted")
finally:
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=15)
'''])
    print(json.dumps({"image": image, "non_root": True, "ocr": "spa+eng",
        "preflight": "ok", "local_api_frontend_worker": "ok", "review_and_exports": "ok", "network": "disabled",
        "public_http_ready": False, "model_calls": 0}))


if __name__ == "__main__":
    main()
