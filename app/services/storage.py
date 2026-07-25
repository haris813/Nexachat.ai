"""Pluggable file-storage backends.

``STORAGE_BACKEND=local`` (default) reads and writes from the local
filesystem exactly as before.  ``STORAGE_BACKEND=s3`` stores artifacts
and uploads in an S3-compatible bucket (AWS S3, Cloudflare R2, Railway
Buckets) while keeping a local temp-write for generation libraries that
require a file path.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import BinaryIO, Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """Minimal contract every storage adapter must satisfy."""

    def save(self, owner_id: str, stored_name: str, data: bytes | BinaryIO) -> str:
        """Persist *data* and return a storage key or absolute path string."""
        ...

    def save_file(self, owner_id: str, stored_name: str, local_path: Path) -> str:
        """Upload a file already written to *local_path* and return the key."""
        ...

    def load(self, storage_key: str) -> bytes:
        """Return the raw bytes for *storage_key*."""
        ...

    def delete(self, storage_key: str) -> None:
        """Remove the object.  Silently succeed when the key does not exist."""
        ...

    def exists(self, storage_key: str) -> bool:
        """Return *True* when the object is reachable."""
        ...

    def presigned_url(self, storage_key: str, *, expires: int = 3600) -> str | None:
        """Return a time-limited download URL, or *None* when not supported."""
        ...


# ── Local filesystem (development default) ────────────────────────────


class LocalStorage:
    """Store files under a configurable local directory.

    ``storage_key`` values are absolute path strings to stay compatible
    with existing ``storage_path`` column contents.
    """

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _owner_dir(self, owner_id: str) -> Path:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:16]
        d = self.base_dir / owner_hash
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, owner_id: str, stored_name: str, data: bytes | BinaryIO) -> str:
        dest = self._owner_dir(owner_id) / stored_name
        raw = data if isinstance(data, bytes) else data.read()
        dest.write_bytes(raw)
        return str(dest)

    def save_file(self, owner_id: str, stored_name: str, local_path: Path) -> str:
        dest = self._owner_dir(owner_id) / stored_name
        if dest.resolve() != local_path.resolve():
            dest.write_bytes(local_path.read_bytes())
        return str(dest)

    def load(self, storage_key: str) -> bytes:
        return Path(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        Path(storage_key).unlink(missing_ok=True)

    def exists(self, storage_key: str) -> bool:
        return Path(storage_key).is_file()

    def presigned_url(self, storage_key: str, *, expires: int = 3600) -> str | None:
        return None  # local storage serves via Flask send_file


# ── S3-compatible object storage ──────────────────────────────────────


class S3Storage:
    """Store objects in an S3-compatible bucket.

    Works with:
    * **AWS S3** — leave ``S3_ENDPOINT`` blank.
    * **Cloudflare R2** — ``S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com``
    * **Railway Buckets** — ``S3_ENDPOINT`` from Railway's bucket service vars.

    ``storage_key`` values are S3 object keys such as
    ``artifacts/<owner_hash>/<stored_name>``.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        region: str = "us-east-1",
        presign_expiry: int = 3600,
        prefix: str = "",
    ) -> None:
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = bucket
        self.presign_expiry = presign_expiry
        self.prefix = prefix.strip("/")

        kwargs: dict = {
            "region_name": region,
            "config": BotoConfig(signature_version="s3v4"),
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key_id:
            kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            kwargs["aws_secret_access_key"] = secret_access_key
        self._client = boto3.client("s3", **kwargs)

    def _object_key(self, owner_id: str, stored_name: str) -> str:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:16]
        parts = [self.prefix, owner_hash, stored_name] if self.prefix else [owner_hash, stored_name]
        return "/".join(parts)

    def save(self, owner_id: str, stored_name: str, data: bytes | BinaryIO) -> str:
        key = self._object_key(owner_id, stored_name)
        body = data if isinstance(data, bytes) else data.read()
        self._client.put_object(Bucket=self.bucket, Key=key, Body=body)
        logger.info("S3 upload bucket=%s key=%s size=%d", self.bucket, key, len(body))
        return key

    def save_file(self, owner_id: str, stored_name: str, local_path: Path) -> str:
        key = self._object_key(owner_id, stored_name)
        self._client.upload_file(str(local_path), self.bucket, key)
        logger.info("S3 upload_file bucket=%s key=%s", self.bucket, key)
        return key

    def load(self, storage_key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=storage_key)
        return response["Body"].read()

    def delete(self, storage_key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=storage_key)
        except Exception:
            logger.warning("S3 delete failed key=%s", storage_key, exc_info=True)

    def exists(self, storage_key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=storage_key)
            return True
        except Exception:
            return False

    def presigned_url(self, storage_key: str, *, expires: int | None = None) -> str | None:
        ttl = expires if expires is not None else self.presign_expiry
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": storage_key},
            ExpiresIn=ttl,
        )


# ── Factory ───────────────────────────────────────────────────────────


def _build_storage(kind: str, config: dict) -> StorageBackend:
    """Instantiate the backend named by *kind*."""
    if kind == "s3":
        bucket = config.get("S3_BUCKET", "")
        if not bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET to be set")
        return S3Storage(
            bucket=bucket,
            endpoint_url=config.get("S3_ENDPOINT", ""),
            access_key_id=config.get("S3_ACCESS_KEY_ID", ""),
            secret_access_key=config.get("S3_SECRET_ACCESS_KEY", ""),
            region=config.get("S3_REGION", "us-east-1"),
            presign_expiry=int(config.get("S3_PRESIGN_EXPIRY", 3600)),
            prefix=config.get("S3_PREFIX", ""),
        )
    # Default: local filesystem
    return LocalStorage(config.get("ARTIFACT_DIR", "data/artifacts"))


_artifact_storage: StorageBackend | None = None
_upload_storage: StorageBackend | None = None


def init_storage(app) -> None:
    """Call once during ``create_app`` to wire up the storage singletons."""
    global _artifact_storage, _upload_storage
    backend = app.config.get("STORAGE_BACKEND", "local").strip().lower()
    if backend == "s3":
        # Both artifact and upload storage share the S3 backend with different prefixes
        _artifact_storage = S3Storage(
            bucket=app.config["S3_BUCKET"],
            endpoint_url=app.config.get("S3_ENDPOINT", ""),
            access_key_id=app.config.get("S3_ACCESS_KEY_ID", ""),
            secret_access_key=app.config.get("S3_SECRET_ACCESS_KEY", ""),
            region=app.config.get("S3_REGION", "us-east-1"),
            presign_expiry=int(app.config.get("S3_PRESIGN_EXPIRY", 3600)),
            prefix="artifacts",
        )
        _upload_storage = S3Storage(
            bucket=app.config["S3_BUCKET"],
            endpoint_url=app.config.get("S3_ENDPOINT", ""),
            access_key_id=app.config.get("S3_ACCESS_KEY_ID", ""),
            secret_access_key=app.config.get("S3_SECRET_ACCESS_KEY", ""),
            region=app.config.get("S3_REGION", "us-east-1"),
            presign_expiry=int(app.config.get("S3_PRESIGN_EXPIRY", 3600)),
            prefix="uploads",
        )
        logger.info("Storage backend: S3 bucket=%s", app.config["S3_BUCKET"])
    else:
        _artifact_storage = LocalStorage(app.config["ARTIFACT_DIR"])
        _upload_storage = LocalStorage(app.config["UPLOAD_DIR"])
        logger.info("Storage backend: local")


def get_artifact_storage() -> StorageBackend:
    """Return the artifact storage singleton."""
    if _artifact_storage is None:
        raise RuntimeError("Storage not initialised; call init_storage() during app startup")
    return _artifact_storage


def get_upload_storage() -> StorageBackend:
    """Return the upload storage singleton."""
    if _upload_storage is None:
        raise RuntimeError("Storage not initialised; call init_storage() during app startup")
    return _upload_storage
