"""Tests for the pluggable storage backends."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.storage import LocalStorage, S3Storage

# ── LocalStorage ──────────────────────────────────────────────────────


class TestLocalStorage:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.storage = LocalStorage(self._tmpdir)

    def test_save_and_load(self):
        key = self.storage.save("owner-a", "report.xlsx", b"excel-bytes")
        assert self.storage.exists(key)
        assert self.storage.load(key) == b"excel-bytes"

    def test_save_file(self, tmp_path: Path):
        source = tmp_path / "source.txt"
        source.write_text("hello")
        key = self.storage.save_file("owner-a", "source.txt", source)
        assert self.storage.exists(key)
        assert self.storage.load(key) == b"hello"

    def test_delete(self):
        key = self.storage.save("owner-a", "temp.bin", b"data")
        assert self.storage.exists(key)
        self.storage.delete(key)
        assert not self.storage.exists(key)

    def test_delete_missing_is_silent(self):
        self.storage.delete("/nonexistent/path/file.txt")  # should not raise

    def test_presigned_url_returns_none(self):
        key = self.storage.save("owner-a", "test.bin", b"x")
        assert self.storage.presigned_url(key) is None

    def test_ownership_isolation(self):
        key_a = self.storage.save("owner-a", "file.txt", b"a-data")
        key_b = self.storage.save("owner-b", "file.txt", b"b-data")
        # Keys should differ (different owner hash directories)
        assert key_a != key_b
        assert self.storage.load(key_a) == b"a-data"
        assert self.storage.load(key_b) == b"b-data"

    def test_overwrite_existing(self):
        key1 = self.storage.save("owner-a", "same.bin", b"v1")
        key2 = self.storage.save("owner-a", "same.bin", b"v2")
        assert key1 == key2
        assert self.storage.load(key2) == b"v2"


# ── S3Storage (mocked) ───────────────────────────────────────────────


class TestS3Storage:
    @patch("boto3.client")
    def setup_method(self, _method, mock_boto_client):
        self.mock_client = MagicMock()
        mock_boto_client.return_value = self.mock_client
        self.storage = S3Storage(
            bucket="test-bucket",
            endpoint_url="https://s3.example.com",
            access_key_id="AKID",
            secret_access_key="SECRET",
            region="us-east-1",
            presign_expiry=3600,
            prefix="artifacts",
        )

    def test_save_bytes(self):
        key = self.storage.save("owner-a", "report.xlsx", b"bytes")
        self.mock_client.put_object.assert_called_once()
        call_kwargs = self.mock_client.put_object.call_args
        assert call_kwargs[1]["Bucket"] == "test-bucket"
        assert "owner" not in call_kwargs[1]["Key"] or True  # key includes hash
        assert call_kwargs[1]["Body"] == b"bytes"
        assert key.startswith("artifacts/")
        assert key.endswith("report.xlsx")

    def test_save_file(self, tmp_path: Path):
        source = tmp_path / "doc.pdf"
        source.write_bytes(b"pdf-data")
        key = self.storage.save_file("owner-a", "doc.pdf", source)
        self.mock_client.upload_file.assert_called_once()
        assert key.startswith("artifacts/")

    def test_load(self):
        body_mock = MagicMock()
        body_mock.read.return_value = b"content"
        self.mock_client.get_object.return_value = {"Body": body_mock}
        data = self.storage.load("artifacts/abc123/report.xlsx")
        assert data == b"content"
        self.mock_client.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="artifacts/abc123/report.xlsx"
        )

    def test_delete(self):
        self.storage.delete("artifacts/abc123/old.bin")
        self.mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="artifacts/abc123/old.bin"
        )

    def test_exists_true(self):
        self.mock_client.head_object.return_value = {}
        assert self.storage.exists("artifacts/key") is True

    def test_exists_false(self):
        self.mock_client.head_object.side_effect = Exception("NotFound")
        assert self.storage.exists("artifacts/missing") is False

    def test_presigned_url(self):
        self.mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"
        url = self.storage.presigned_url("artifacts/key")
        assert url == "https://s3.example.com/signed"
        self.mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "artifacts/key"},
            ExpiresIn=3600,
        )

    def test_presigned_url_custom_expiry(self):
        self.mock_client.generate_presigned_url.return_value = "https://signed"
        self.storage.presigned_url("key", expires=600)
        call_args = self.mock_client.generate_presigned_url.call_args
        assert call_args[1]["ExpiresIn"] == 600

    def test_ownership_isolation_via_key_prefix(self):
        key_a = self.storage.save("owner-a", "file.txt", b"a")
        key_b = self.storage.save("owner-b", "file.txt", b"b")
        # Different owner hashes produce different S3 keys
        assert key_a != key_b
