"""AWS Batch job submission and polling — tool functions and submitter class."""

from __future__ import annotations

import logging
from typing import Literal

import boto3
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Pydantic schemas (mirror tool_contracts.md section 11) ────────────────────


class BatchJobInput(BaseModel):
    job_name: str
    job_queue: str
    job_definition: str
    container_overrides: dict
    depends_on: list[str] = []


class BatchJobOutput(BaseModel):
    job_id: str
    job_arn: str
    status: str


class BatchPollInput(BaseModel):
    job_id: str


class BatchPollOutput(BaseModel):
    job_id: str
    status: Literal[
        "SUBMITTED", "PENDING", "RUNNABLE", "STARTING", "RUNNING", "SUCCEEDED", "FAILED"
    ]
    status_reason: str | None = None
    exit_code: int | None = None
    log_stream_name: str | None = None


# ── Standalone tool functions ──────────────────────────────────────────────────


def submit_aws_batch_job(
    inp: BatchJobInput,
    *,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
) -> BatchJobOutput:
    """Submit a containerized job to AWS Batch and return the job handle."""
    client = boto3.client("batch", region_name=region, endpoint_url=endpoint_url)
    depends = [{"jobId": jid} for jid in inp.depends_on]
    logger.debug("batch submit: job_name=%s queue=%s", inp.job_name, inp.job_queue)
    resp = client.submit_job(
        jobName=inp.job_name,
        jobQueue=inp.job_queue,
        jobDefinition=inp.job_definition,
        containerOverrides=inp.container_overrides,
        dependsOn=depends,
    )
    return BatchJobOutput(
        job_id=resp["jobId"],
        job_arn=resp.get("jobArn", f"arn:aws:batch:{region}:000000000000:job/{resp['jobId']}"),
        status="SUBMITTED",
    )


def poll_aws_batch_job(
    inp: BatchPollInput,
    *,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
) -> BatchPollOutput:
    """Poll an AWS Batch job and return its current status."""
    client = boto3.client("batch", region_name=region, endpoint_url=endpoint_url)
    logger.debug("batch poll: job_id=%s", inp.job_id)
    resp = client.describe_jobs(jobs=[inp.job_id])
    jobs = resp.get("jobs", [])
    if not jobs:
        raise ValueError(f"No Batch job found for job_id={inp.job_id!r}")
    job = jobs[0]
    container = job.get("container", {})
    return BatchPollOutput(
        job_id=job["jobId"],
        status=job["status"],
        status_reason=job.get("statusReason"),
        exit_code=container.get("exitCode"),
        log_stream_name=container.get("logStreamName"),
    )


# ── Class wrapper ──────────────────────────────────────────────────────────────


class AWSBatchSubmitter:
    """Stateful wrapper that reuses a boto3 Batch client across calls."""

    def __init__(
        self,
        *,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ) -> None:
        self._client = boto3.client("batch", region_name=region, endpoint_url=endpoint_url)
        self._region = region

    def submit(self, inp: BatchJobInput) -> BatchJobOutput:
        depends = [{"jobId": jid} for jid in inp.depends_on]
        logger.debug("batch submit: job_name=%s queue=%s", inp.job_name, inp.job_queue)
        resp = self._client.submit_job(
            jobName=inp.job_name,
            jobQueue=inp.job_queue,
            jobDefinition=inp.job_definition,
            containerOverrides=inp.container_overrides,
            dependsOn=depends,
        )
        return BatchJobOutput(
            job_id=resp["jobId"],
            job_arn=resp.get(
                "jobArn",
                f"arn:aws:batch:{self._region}:000000000000:job/{resp['jobId']}",
            ),
            status="SUBMITTED",
        )

    def poll(self, inp: BatchPollInput) -> BatchPollOutput:
        logger.debug("batch poll: job_id=%s", inp.job_id)
        resp = self._client.describe_jobs(jobs=[inp.job_id])
        jobs = resp.get("jobs", [])
        if not jobs:
            raise ValueError(f"No Batch job found for job_id={inp.job_id!r}")
        job = jobs[0]
        container = job.get("container", {})
        return BatchPollOutput(
            job_id=job["jobId"],
            status=job["status"],
            status_reason=job.get("statusReason"),
            exit_code=container.get("exitCode"),
            log_stream_name=container.get("logStreamName"),
        )
