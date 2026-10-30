"""Private, content-addressed originals. No user filename becomes a storage path."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class DocumentReference:
    key: str
    sha256: str
    size: int


def document_key(sha256: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("La huella documental no es válida.")
    return f"originals/{sha256[:2]}/{sha256}.pdf"


def verify_content(content: bytes, sha256: str, size: int) -> bytes:
    if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError("El original no coincide con su tamaño o huella documental. No se utilizó.")
    return content


class FileDocumentStorage:
    def __init__(self, root: Path, *, create: bool = True):
        self.root = root.resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key: str, sha256: str) -> Path:
        if key != document_key(sha256):
            raise ValueError("La referencia documental no es válida.")
        path = self.root / key
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("La referencia documental está fuera del almacenamiento autorizado.")
        return path

    def put(self, content: bytes) -> DocumentReference:
        digest = hashlib.sha256(content).hexdigest()
        reference = DocumentReference(document_key(digest), digest, len(content))
        path = self._path(reference.key, digest)
        if path.exists():
            self.read(reference.key, digest, len(content))
            return reference
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return reference

    def read(self, key: str, sha256: str, size: int) -> bytes:
        path = self._path(key, sha256)
        with path.open("rb") as source:
            return verify_content(source.read(size + 1), sha256, size)


class AzureDocumentStorage:
    def __init__(self, *, account_url: str = "", container: str, connection_string: str = "",
                 credential=None, allow_emulator: bool = False):
        from azure.storage.blob import BlobServiceClient
        self._credential = None
        options = {"retry_total": 2, "connection_timeout": 5, "read_timeout": 30}
        if allow_emulator:
            options["api_version"] = "2023-11-03"
        if connection_string:
            self.client = BlobServiceClient.from_connection_string(connection_string, **options)
        else:
            if credential is None:
                from azure.identity import ManagedIdentityCredential
                self._credential = ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID") or None)
                credential = self._credential
            self.client = BlobServiceClient(account_url=account_url, credential=credential, **options)
        endpoint = urlparse(self.client.url)
        local_emulator = allow_emulator and endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
        if endpoint.scheme != "https" and not local_emulator:
            self.close()
            raise ValueError("El almacenamiento Azure requiere HTTPS.")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", container):
            self.close()
            raise ValueError("El nombre del contenedor documental no es válido.")
        self.container = self.client.get_container_client(container)

    def put(self, content: bytes) -> DocumentReference:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings
        digest = hashlib.sha256(content).hexdigest()
        reference = DocumentReference(document_key(digest), digest, len(content))
        blob = self.container.get_blob_client(reference.key)
        try:
            blob.upload_blob(content, overwrite=False, metadata={"sha256": digest},
                             content_settings=ContentSettings(content_type="application/pdf"),
                             max_concurrency=1, timeout=30)
        except ResourceExistsError:
            # A storage key alone does not prove the original is intact.
            self.read(reference.key, digest, len(content))
        return reference

    def read(self, key: str, sha256: str, size: int) -> bytes:
        if key != document_key(sha256):
            raise ValueError("La referencia documental no es válida.")
        blob = self.container.get_blob_client(key)
        properties = blob.get_blob_properties(timeout=30)
        if properties.size != size:
            raise ValueError("El tamaño del original almacenado no coincide.")
        content = blob.download_blob(offset=0, length=size + 1, max_concurrency=1, timeout=30).readall()
        return verify_content(content, sha256, size)

    def close(self):
        self.client.close()
        if self._credential is not None:
            self._credential.close()
