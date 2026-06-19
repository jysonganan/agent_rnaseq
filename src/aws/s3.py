"""S3FileManager: upload, download, list, presign, and existence-check for S3 objects."""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3FileManager:
    """Thin wrapper around boto3 S3 operations.

    All methods accept full ``s3://bucket/key`` URIs so callers never have to
    split URIs themselves.  The default *bucket* passed at construction is
    stored for reference but the URI always takes precedence.
    """

    def __init__(
        self,
        bucket: str,
        *,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
        )

    # ── URI helpers ────────────────────────────────────────────────────────────

    def _parse_s3_uri(self, s3_uri: str) -> tuple[str, str]:
        """Return *(bucket, key)* from ``s3://bucket/key``."""
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"S3 URI must start with 's3://', got: {s3_uri!r}")
        without_scheme = s3_uri[5:]
        bucket, _, key = without_scheme.partition("/")
        return bucket, key

    # ── Public API ─────────────────────────────────────────────────────────────

    def upload(self, local_path: str, s3_uri: str) -> None:
        """Upload *local_path* to *s3_uri*."""
        bucket, key = self._parse_s3_uri(s3_uri)
        logger.debug("s3 upload: %s → %s", local_path, s3_uri)
        self._client.upload_file(local_path, bucket, key)

    def download(self, s3_uri: str, local_path: str) -> None:
        """Download *s3_uri* to *local_path*, creating parent directories as needed."""
        bucket, key = self._parse_s3_uri(s3_uri)
        parent = os.path.dirname(local_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        logger.debug("s3 download: %s → %s", s3_uri, local_path)
        self._client.download_file(bucket, key, local_path)

    def list(self, s3_prefix: str) -> list[str]:
        """Return all object URIs under *s3_prefix*."""
        bucket, prefix = self._parse_s3_uri(s3_prefix)
        paginator = self._client.get_paginator("list_objects_v2")
        uris: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                uris.append(f"s3://{bucket}/{obj['Key']}")
        return uris

    def presign(self, s3_uri: str, expires_in: int = 3600) -> str:
        """Return a pre-signed GET URL for *s3_uri* valid for *expires_in* seconds."""
        bucket, key = self._parse_s3_uri(s3_uri)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def exists(self, s3_uri: str) -> bool:
        """Return ``True`` if the object at *s3_uri* exists."""
        bucket, key = self._parse_s3_uri(s3_uri)
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False
