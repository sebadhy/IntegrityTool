"""Synthetic signed-token test executed only inside the isolated smoke container.

The runner disables networking. Its child replaces only public-key retrieval;
the production token signature, claims, roles and route checks execute unchanged.
No test switch or test key is included in the application image.
"""
import json
import os
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import jwt
import pymupdf
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

tenant = "11111111-1111-4111-8111-111111111111"
client = "22222222-2222-4222-8222-222222222222"
user = "33333333-3333-4333-8333-333333333333"
origin = "https://integrity.test"
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_pem = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
environment = dict(os.environ, INTEGRITY_WEB_MODE="entra", INTEGRITY_WORKER_MODE="external",
    INTEGRITY_PUBLIC_ORIGIN=origin, INTEGRITY_ENTRA_TENANT_ID=tenant, INTEGRITY_ENTRA_CLIENT_ID=client,
    INTEGRITY_ACCESS_POLICY="shared_team", INTEGRITY_ASSISTED_ENABLED="false",
    INTEGRITY_STORE_PATH="/tmp/secure-smoke/reviews.sqlite3", INTEGRITY_DOCUMENT_STORAGE="filesystem",
    INTEGRITY_DOCUMENTS_PATH="/tmp/secure-smoke/documents")
script = f'''
import jwt, uvicorn
from types import SimpleNamespace
from cryptography.hazmat.primitives.serialization import load_pem_public_key
public_key = load_pem_public_key({public_pem!r}.encode())
jwt.PyJWKClient.get_signing_key_from_jwt = lambda self, token: SimpleNamespace(key=public_key)
from src.workbench_api import app
uvicorn.run(app, host="0.0.0.0", port=8001, proxy_headers=False)
'''
process = subprocess.Popen([sys.executable, "-c", script], env=environment)


def auth(role):
    now = int(time.time())
    return jwt.encode({"exp": now + 600, "iat": now - 10, "nbf": now - 10,
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0", "aud": client, "tid": tenant,
        "oid": user, "sub": "synthetic-user", "nonce": "synthetic-nonce", "ver": "2.0",
        "roles": [role]}, private_key, algorithm="RS256", headers={"kid": "synthetic"})


def call(path, *, token=None, method="GET", body=None, content_type=None, extra=None):
    headers = {"Host": "integrity.test", "Origin": origin, **(extra or {})}
    if token:
        headers["X-MS-TOKEN-AAD-ID-TOKEN"] = token
    if content_type:
        headers["Content-Type"] = content_type
    request = Request("http://127.0.0.1:8001" + path, data=body, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read()


try:
    for _ in range(100):
        try:
            if call("/healthz")[0] == 200:
                break
        except URLError:
            if process.poll() is not None:
                raise AssertionError("Secure API failed to start")
        time.sleep(.1)
    else:
        raise AssertionError("Secure API startup timeout")
    writer, reader = auth("Integrity.Reviewer"), auth("Integrity.Reader")
    assert call("/")[0] == 200
    assert call("/api/cases")[0] == 401
    assert call("/api/cases", extra={"X-MS-CLIENT-PRINCIPAL": "forged", "X-MS-TOKEN-AAD-ID-TOKEN": "forged"})[0] == 401
    assert call("/api/session", token=reader)[0] == 200
    assert call("/api/cases", token=reader, method="POST")[0] == 403
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Debe ser distribuidor autorizado exclusivo del fabricante X.")
    original = document.tobytes()
    document.close()
    boundary = "secure-container-fixture"
    fields = []
    for name, value in (("manifest", '[{"role":"pliego"}]'), ("request_key", "secure-fixture")):
        fields.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    fields.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="test.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode() + original + b"\r\n")
    fields.append(f"--{boundary}--\r\n".encode())
    status, payload = call("/api/cases", token=writer, method="POST", body=b"".join(fields), content_type=f"multipart/form-data; boundary={boundary}")
    assert status == 202
    case_id = json.loads(payload)["id"]
    subprocess.run([sys.executable, "-m", "src.review_worker", "--once"], env=environment, check=True, timeout=45)
    endpoint = f"/api/cases/{case_id}"
    case = json.loads(call(endpoint, token=reader)[1])
    assert case["status"] == "ready" and case["result"]["items"]
    item = case["result"]["items"][0]["id"]
    update = json.dumps({"state": "followup", "comment": "Prueba", "reviewer": "spoofed", "expected_revision": 0}).encode()
    status, payload = call(endpoint + f"/items/{item}/review", token=writer, method="PUT", body=update, content_type="application/json")
    assert status == 200 and json.loads(payload)["reviewer"] == f"entra:{tenant}:{user}"
    for path in (endpoint, endpoint + f"/documents/{case['documents'][0]['id']}", endpoint + "/taxonomy",
                 endpoint + "/history", *[endpoint + "/export?format=" + format for format in ("html", "csv", "json")]):
        assert call(path)[0] == 401
        assert call(path, token=reader)[0] == 200
    assert call(endpoint + "/retry", token=writer, method="POST", extra={"Origin": "https://attacker.invalid"})[0] == 403
    print(json.dumps({"signed_identity": "ok", "reader_writer_roles": "ok", "protected_documents_and_exports": "ok", "model_calls": 0}))
finally:
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=15)
