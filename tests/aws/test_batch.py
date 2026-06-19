"""Tests for AWSBatchSubmitter and tool functions — mocked with moto."""

from __future__ import annotations

import json
import logging

import boto3
import pytest
from moto import mock_aws

from src.aws.batch import (
    AWSBatchSubmitter,
    BatchJobInput,
    BatchPollInput,
    poll_aws_batch_job,
    submit_aws_batch_job,
)

REGION = "us-east-1"
JOB_QUEUE = "test-queue"
JOB_DEF = "test-def"


@pytest.fixture
def batch_env():
    """Yield a dict with queue/def names inside a fully-mocked AWS Batch environment."""
    with mock_aws():
        iam = boto3.client("iam", region_name=REGION)
        batch = boto3.client("batch", region_name=REGION)

        role = iam.create_role(
            RoleName="BatchServiceRole",
            AssumeRolePolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "batch.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
        )
        role_arn = role["Role"]["Arn"]

        batch.create_compute_environment(
            computeEnvironmentName="test-ce",
            type="UNMANAGED",
            state="ENABLED",
            serviceRole=role_arn,
        )

        batch.create_job_queue(
            jobQueueName=JOB_QUEUE,
            state="ENABLED",
            priority=1,
            computeEnvironmentOrder=[{"order": 1, "computeEnvironment": "test-ce"}],
        )

        batch.register_job_definition(
            jobDefinitionName=JOB_DEF,
            type="container",
            containerProperties={"image": "busybox", "vcpus": 1, "memory": 512},
        )

        yield {"queue": JOB_QUEUE, "definition": JOB_DEF, "client": batch}


# ── submit_aws_batch_job tool function ────────────────────────────────────────


def test_submit_returns_job_id(batch_env):
    inp = BatchJobInput(
        job_name="align-job-001",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={"command": ["nextflow", "run", "main.nf"]},
    )
    out = submit_aws_batch_job(inp, region=REGION)
    assert out.job_id
    # Must be a non-empty string (UUID-like)
    assert len(out.job_id) > 8


def test_submit_returns_job_arn(batch_env):
    inp = BatchJobInput(
        job_name="align-job-002",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    out = submit_aws_batch_job(inp, region=REGION)
    assert out.job_arn.startswith("arn:aws:batch:")


def test_submit_status_is_submitted(batch_env):
    inp = BatchJobInput(
        job_name="align-job-003",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    out = submit_aws_batch_job(inp, region=REGION)
    assert out.status == "SUBMITTED"


def test_submit_with_depends_on(batch_env):
    """Submit a first job; submit a second that depends on it. Both should succeed."""
    inp1 = BatchJobInput(
        job_name="job-a",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    out1 = submit_aws_batch_job(inp1, region=REGION)
    inp2 = BatchJobInput(
        job_name="job-b",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
        depends_on=[out1.job_id],
    )
    out2 = submit_aws_batch_job(inp2, region=REGION)
    assert out2.job_id != out1.job_id


# ── poll_aws_batch_job tool function ──────────────────────────────────────────


def test_poll_returns_batch_poll_output(batch_env):
    inp = BatchJobInput(
        job_name="quant-job-001",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    submitted = submit_aws_batch_job(inp, region=REGION)
    result = poll_aws_batch_job(BatchPollInput(job_id=submitted.job_id), region=REGION)
    assert result.job_id == submitted.job_id


def test_poll_status_valid_literal(batch_env):
    valid_statuses = {
        "SUBMITTED", "PENDING", "RUNNABLE", "STARTING", "RUNNING", "SUCCEEDED", "FAILED"
    }
    inp = BatchJobInput(
        job_name="quant-job-002",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    submitted = submit_aws_batch_job(inp, region=REGION)
    result = poll_aws_batch_job(BatchPollInput(job_id=submitted.job_id), region=REGION)
    assert result.status in valid_statuses


def test_poll_unknown_job_raises(batch_env):
    with pytest.raises(ValueError, match="No Batch job found"):
        poll_aws_batch_job(BatchPollInput(job_id="00000000-0000-0000-0000-000000000000"), region=REGION)


# ── AWSBatchSubmitter class ───────────────────────────────────────────────────


def test_submitter_class_submit_returns_job_id(batch_env):
    submitter = AWSBatchSubmitter(region=REGION)
    inp = BatchJobInput(
        job_name="de-job-001",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    out = submitter.submit(inp)
    assert out.job_id


def test_submitter_class_poll_returns_status(batch_env):
    submitter = AWSBatchSubmitter(region=REGION)
    inp = BatchJobInput(
        job_name="de-job-002",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    submitted = submitter.submit(inp)
    polled = submitter.poll(BatchPollInput(job_id=submitted.job_id))
    assert polled.status in {"SUBMITTED", "PENDING", "RUNNABLE", "STARTING", "RUNNING", "SUCCEEDED", "FAILED"}


def test_submitter_poll_unknown_raises(batch_env):
    submitter = AWSBatchSubmitter(region=REGION)
    with pytest.raises(ValueError, match="No Batch job found"):
        submitter.poll(BatchPollInput(job_id="nonexistent-job-id"))


# ── no credentials in log output ──────────────────────────────────────────────


def test_no_credentials_in_batch_logs(batch_env, monkeypatch, caplog):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKEBATCHCRED001")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "batchsupersecretkey000000000000000000000")
    inp = BatchJobInput(
        job_name="cred-test-job",
        job_queue=batch_env["queue"],
        job_definition=batch_env["definition"],
        container_overrides={},
    )
    with caplog.at_level(logging.DEBUG, logger="src.aws.batch"):
        out = submit_aws_batch_job(inp, region=REGION)
        poll_aws_batch_job(BatchPollInput(job_id=out.job_id), region=REGION)
    assert "AKIAFAKEBATCHCRED001" not in caplog.text
    assert "batchsupersecretkey000000000000000000000" not in caplog.text
