"""Uniform access to stage outputs on local disk or S3.

The Nextflow backend publishes results either to a local directory (``executor=nextflow``)
or to S3 (``executor=aws_batch``). The worker only needs to check that expected files exist
and to read *small* files (logs, counts, FastQC zips, VCFs) locally for parsing; large files
such as BAMs are referenced by URI and never downloaded unless a worker-side stage needs them.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
from typing import Protocol


class Storage(Protocol):
    def join(self, *parts: str) -> str: ...
    def exists(self, path: str) -> bool: ...
    def localize(self, path: str) -> str: ...


class LocalStorage:
    def join(self, *parts: str) -> str:
        return os.path.join(*parts)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def localize(self, path: str) -> str:
        return path


class S3Storage:
    """S3 URIs; ``localize`` downloads into a per-run cache directory (once)."""

    def __init__(self, manager: object, cache_dir: str) -> None:
        self._s3 = manager
        self._cache_dir = cache_dir

    def join(self, *parts: str) -> str:
        return posixpath.join(*parts)

    def exists(self, path: str) -> bool:
        if not path.startswith("s3://"):
            return os.path.exists(path)
        if self._s3.exists(path):  # type: ignore[attr-defined]
            return True
        # "directories" (e.g. Salmon output) exist if any object has the prefix
        return bool(self._s3.list(path.rstrip("/") + "/"))  # type: ignore[attr-defined]

    def localize(self, path: str) -> str:
        if not path.startswith("s3://"):
            return path
        # Hash the parent prefix so siblings (BAM + .bai) land in the same directory.
        digest = hashlib.sha1(posixpath.dirname(path).encode()).hexdigest()[:12]
        local = os.path.join(self._cache_dir, digest, posixpath.basename(path))
        if not os.path.exists(local):
            self._s3.download(path, local)  # type: ignore[attr-defined]
        return local


def storage_for(path: str, cache_dir: str) -> Storage:
    if path.startswith("s3://"):
        from src.aws.config import get_aws_config
        from src.aws.s3 import S3FileManager

        cfg = get_aws_config()
        manager = S3FileManager(cfg.bucket, region=cfg.region, endpoint_url=cfg.endpoint_url)
        return S3Storage(manager, cache_dir)
    return LocalStorage()
