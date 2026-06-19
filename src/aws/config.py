"""AWS configuration derived from application settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AWSConfig:
    region: str
    bucket: str
    batch_job_queue: str
    batch_job_definition: str
    endpoint_url: str | None  # None → real AWS; set for LocalStack / MinIO


def get_aws_config() -> AWSConfig:
    from src.config import get_settings

    s = get_settings()
    return AWSConfig(
        region=s.aws_default_region,
        bucket=s.s3_artifact_bucket,
        batch_job_queue=s.aws_batch_job_queue,
        batch_job_definition=s.aws_batch_job_definition,
        endpoint_url=s.aws_endpoint_url or None,
    )
