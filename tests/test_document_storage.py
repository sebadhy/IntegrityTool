import hashlib
import os
import uuid
from urllib.parse import urlparse

import pytest

from src.analyzer.document_storage import AzureDocumentStorage, FileDocumentStorage, document_key


def test_file_original_has_deterministic_key_and_detects_corruption(tmp_path):
    storage = FileDocumentStorage(tmp_path / "objects")
    content = b"%PDF-original-for-local-test"
    first = storage.put(content)
    second = storage.put(content)
    assert first == second
    assert first.key == document_key(hashlib.sha256(content).hexdigest())
    assert storage.read(first.key, first.sha256, first.size) == content
    (storage.root / first.key).write_bytes(b"changed")
    with pytest.raises(ValueError, match="huella"):
        storage.read(first.key, first.sha256, first.size)


@pytest.mark.parametrize("key", ["../outside.pdf", "/tmp/outside.pdf", "originals/wrong.pdf"])
def test_file_reference_cannot_escape_its_content_identity(tmp_path, key):
    storage = FileDocumentStorage(tmp_path / "objects")
    with pytest.raises(ValueError):
        storage.read(key, "a" * 64, 100)


def test_symlink_cannot_redirect_an_original_outside_storage(tmp_path):
    storage = FileDocumentStorage(tmp_path / "objects")
    reference = storage.put(b"%PDF-local")
    path = storage.root / reference.key
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-local")
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("This system does not permit unprivileged symlinks.")
    with pytest.raises(ValueError, match="fuera"):
        storage.read(reference.key, reference.sha256, reference.size)


@pytest.fixture
def azure_storage():
    endpoint = os.getenv("INTEGRITY_TEST_AZURITE_URL")
    if not endpoint:
        pytest.skip("Set INTEGRITY_TEST_AZURITE_URL for the local storage emulator.")
    if urlparse(endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Storage integration only accepts the local emulator, never an Azure account.")
    from azure.core.credentials import AzureNamedKeyCredential
    name = "integrity-" + uuid.uuid4().hex
    # This account/key is public test configuration, not an Azure credential.
    storage = AzureDocumentStorage(account_url=endpoint, container=name,
        credential=AzureNamedKeyCredential("integritytest", "bG9jYWwtdGVzdC1vbmx5LWtleQ=="),
        allow_emulator=True)
    storage.container.create_container()
    try:
        yield storage
    finally:
        storage.container.delete_container()
        storage.close()


def test_azure_emulator_put_read_deduplication_and_corruption(azure_storage):
    content = b"%PDF-original-used-only-in-the-emulator"
    first = azure_storage.put(content)
    assert azure_storage.put(content) == first
    assert azure_storage.read(first.key, first.sha256, first.size) == content
    blob = azure_storage.container.get_blob_client(first.key)
    blob.upload_blob(b"X" * len(content), overwrite=True)
    with pytest.raises(ValueError, match="huella"):
        azure_storage.read(first.key, first.sha256, first.size)


def test_azure_document_cannot_be_requested_with_another_key(azure_storage):
    with pytest.raises(ValueError, match="referencia"):
        azure_storage.read("originals/wrong.pdf", "a" * 64, 10)
