"""
Photo storage — local disk for development, Cloudflare R2 for deployment.

Why this exists
---------------
Photos were written with ``dest.write_bytes(contents)`` to a path under
``/tmp``. That is correct on a workstation and wrong on every deployment
target: a container filesystem is ephemeral, so the row in ``logsheet_photos``
would keep pointing at a file the next restart had already destroyed. The
database would look healthy and the evidence would be gone.

R2 is the deployment backend (see
``docs/asset-storage-cloudflare-cloudinary-neondb.md``): 10 GB free, zero
egress fees, and — the part that matters for logsheets — it stores bytes
verbatim rather than re-encoding them, so fine detail in a site photo survives.

Selection is by configuration, not by branching at the call site:

    FIELD_OPS_STORAGE_BACKEND=local   (default; dev)
    FIELD_OPS_STORAGE_BACKEND=r2      (deployment)

Fail-closed
-----------
Choosing ``r2`` without complete credentials raises before any request is
served, not at first upload. Two things enforce that, because this function is
otherwise only reached from the photo endpoint:

* ``config._assert_deployable`` includes the four R2 variables in the
  production gate, so the process refuses to start.
* ``main._init_storage`` resolves the backend on the FastAPI startup event, so
  even outside production the failure lands while someone is watching the
  deploy rather than on an operator's phone.

A service that accepts a photo and silently drops it is worse than one that
refuses to boot: by then the operator has already left the site.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from field_ops.config import settings


class PhotoStorage(ABC):
    """Stores photo bytes and returns a stable reference for the DB row."""

    @abstractmethod
    async def save(self, logsheet_id: int, filename: str, content: bytes) -> str:
        """Persist and return the storage reference recorded in the database."""


class LocalDiskStorage(PhotoStorage):
    """Development backend. Not suitable for any deployment target."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)

    async def save(self, logsheet_id: int, filename: str, content: bytes) -> str:
        target_dir = self.base_dir / str(logsheet_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / _safe_key(filename)
        dest.write_bytes(content)
        return str(dest)


class R2Storage(PhotoStorage):
    """
    Cloudflare R2 via its S3-compatible API.

    boto3 is synchronous, so the upload runs in a worker thread — blocking the
    event loop on a multi-megabyte upload would stall every other request on
    the instance, and field uploads are large and slow by nature.
    """

    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
    ) -> None:
        import boto3  # imported lazily so local dev needs no AWS SDK

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",  # R2 ignores region but boto3 requires one
        )

    async def save(self, logsheet_id: int, filename: str, content: bytes) -> str:
        import asyncio

        key = f"logsheets/{logsheet_id}/{_safe_key(filename)}"

        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=_content_type(filename),
        )

        # Store the key, never a presigned URL: presigned URLs expire, and a
        # database full of dead links is indistinguishable from lost data.
        # Read paths mint a fresh URL from this key on demand.
        return f"r2://{self.bucket}/{key}"


def _safe_key(filename: str) -> str:
    """
    Prefix a UUID and strip any path component.

    Two reasons, both real: phone cameras produce colliding names
    (``IMG_0001.jpg`` from two devices on the same day), and an attacker-
    supplied ``../`` in a filename must not escape the prefix.
    """
    stem = Path(filename or "photo.jpg").name
    return f"{uuid.uuid4().hex}_{stem}"


def _content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".heic": "image/heic",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


_storage: PhotoStorage | None = None


def get_storage() -> PhotoStorage:
    """Resolve the configured backend once, and validate it eagerly."""
    global _storage
    if _storage is not None:
        return _storage

    backend = (settings.field_ops_storage_backend or "local").lower()

    if backend == "local":
        _storage = LocalDiskStorage(settings.field_ops_upload_dir)
        return _storage

    if backend == "r2":
        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", settings.r2_account_id),
                ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
                ("R2_BUCKET", settings.r2_bucket),
            )
            if not value
        ]
        if missing:
            # Names only — never echo a credential value into logs or an
            # exception that might be shipped to an error tracker.
            raise RuntimeError(
                "FIELD_OPS_STORAGE_BACKEND=r2 but these are unset: "
                + ", ".join(missing)
            )

        _storage = R2Storage(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket=settings.r2_bucket,
        )
        return _storage

    raise RuntimeError(
        f"Unknown FIELD_OPS_STORAGE_BACKEND={backend!r} (expected 'local' or 'r2')"
    )
