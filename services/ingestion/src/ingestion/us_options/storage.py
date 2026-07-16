"""Immutable object storage for licensed research inputs and normalized artifacts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from bulls.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    sha256: str
    size_bytes: int


class ImmutableObjectStore(Protocol):
    def put(
        self,
        *,
        key: str,
        payload: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...

    def get(self, *, key: str, max_bytes: int) -> bytes: ...


def _validated_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe object key: {key!r}")
    return path


class LocalImmutableObjectStore:
    """Development/test backend with the same write-once contract as production S3."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def put(
        self,
        *,
        key: str,
        payload: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        del content_type, metadata
        relative = _validated_key(key)
        destination = self.root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(payload).hexdigest()
        if destination.exists():
            existing = destination.read_bytes()
            if hashlib.sha256(existing).hexdigest() != digest:
                raise RuntimeError(f"immutable object collision at {key}")
            return StoredObject(key=key, sha256=digest, size_bytes=len(existing))
        try:
            with destination.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            existing = destination.read_bytes()
            if hashlib.sha256(existing).hexdigest() != digest:
                raise RuntimeError(f"immutable object collision at {key}") from None
        return StoredObject(key=key, sha256=digest, size_bytes=len(payload))

    def get(self, *, key: str, max_bytes: int) -> bytes:
        relative = _validated_key(key)
        source = self.root.joinpath(*relative.parts)
        metadata = source.stat()
        if metadata.st_size > max_bytes:
            raise ValueError(f"research object exceeds {max_bytes} bytes: {key}")
        payload = source.read_bytes()
        if len(payload) > max_bytes:
            raise ValueError(f"research object exceeds {max_bytes} bytes: {key}")
        return payload


class S3ImmutableObjectStore:
    """Content-addressed S3 writer using a conditional create to prevent overwrites."""

    def __init__(self, *, bucket: str, prefix: str = "", region: str = "") -> None:
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", region_name=region or None)

    def _key(self, key: str) -> str:
        _validated_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(
        self,
        *,
        key: str,
        payload: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        from botocore.exceptions import ClientError

        digest = hashlib.sha256(payload).hexdigest()
        full_key = self._key(key)
        object_metadata = {"sha256": digest, **(metadata or {})}
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=full_key,
                Body=payload,
                ContentType=content_type,
                Metadata=object_metadata,
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status not in {409, 412}:
                raise
            head = self.client.head_object(Bucket=self.bucket, Key=full_key)
            if head.get("Metadata", {}).get("sha256") != digest:
                raise RuntimeError(f"immutable object collision at {full_key}") from exc
        return StoredObject(key=key, sha256=digest, size_bytes=len(payload))

    def get(self, *, key: str, max_bytes: int) -> bytes:
        full_key = self._key(key)
        response = self.client.get_object(Bucket=self.bucket, Key=full_key)
        size = int(response.get("ContentLength") or 0)
        if size > max_bytes:
            response["Body"].close()
            raise ValueError(f"research object exceeds {max_bytes} bytes: {key}")
        try:
            payload = response["Body"].read(max_bytes + 1)
        finally:
            response["Body"].close()
        if len(payload) > max_bytes:
            raise ValueError(f"research object exceeds {max_bytes} bytes: {key}")
        expected_hash = response.get("Metadata", {}).get("sha256")
        if expected_hash and hashlib.sha256(payload).hexdigest() != expected_hash:
            raise RuntimeError(f"research object hash mismatch at {key}")
        return payload


def object_store(settings: Settings | None = None) -> ImmutableObjectStore:
    configured = settings or get_settings()
    if configured.research_object_store_backend == "local":
        return LocalImmutableObjectStore(configured.research_object_store_local_dir)
    if configured.research_object_store_backend == "s3":
        return S3ImmutableObjectStore(
            bucket=configured.research_object_store_s3_bucket,
            prefix=configured.research_object_store_s3_prefix,
            region=configured.research_object_store_aws_region,
        )
    raise RuntimeError("research object storage is disabled")
