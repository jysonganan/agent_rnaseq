"""Integration test: S3 artifact upload/download with moto mock."""

from __future__ import annotations

import os
import tempfile

import pytest

try:
    import boto3
    from moto import mock_aws

    _HAS_MOTO = True
except ImportError:
    _HAS_MOTO = False

pytestmark = pytest.mark.skipif(not _HAS_MOTO, reason="moto not installed")

from src.aws.s3 import S3FileManager  # noqa: E402


@pytest.fixture(autouse=True)
def aws_credentials():
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
    os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    yield


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-pipeline-bucket")
        yield "test-pipeline-bucket"


def test_upload_then_exists(s3_bucket):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
        mgr = S3FileManager(s3_bucket, region="us-east-1")
        with tempfile.NamedTemporaryFile(suffix=".bam", delete=False) as f:
            f.write(b"mock bam content")
            local_path = f.name
        mgr.upload(local_path, f"s3://{s3_bucket}/align/sample.bam")
        assert mgr.exists(f"s3://{s3_bucket}/align/sample.bam")


def test_upload_then_list(s3_bucket):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
        mgr = S3FileManager(s3_bucket, region="us-east-1")
        with tempfile.NamedTemporaryFile(suffix=".vcf", delete=False) as f:
            f.write(b"##fileformat=VCFv4.2\n")
            local_path = f.name
        mgr.upload(local_path, f"s3://{s3_bucket}/variant/result.vcf")
        objects = mgr.list(f"s3://{s3_bucket}/variant/")
        assert f"s3://{s3_bucket}/variant/result.vcf" in objects


def test_download_recovers_content(s3_bucket, tmp_path):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
        mgr = S3FileManager(s3_bucket, region="us-east-1")
        content = b"normalized counts mock data"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(content)
            upload_path = f.name
        mgr.upload(upload_path, f"s3://{s3_bucket}/de/normalized_counts.csv")
        download_path = str(tmp_path / "downloaded.csv")
        mgr.download(f"s3://{s3_bucket}/de/normalized_counts.csv", download_path)
        with open(download_path, "rb") as fh:
            assert fh.read() == content


def test_nonexistent_key_not_exists(s3_bucket):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
        mgr = S3FileManager(s3_bucket, region="us-east-1")
        assert not mgr.exists(f"s3://{s3_bucket}/does/not/exist.bam")


def test_presign_returns_url(s3_bucket):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
        mgr = S3FileManager(s3_bucket, region="us-east-1")
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(b"<html/>")
            local_path = f.name
        mgr.upload(local_path, f"s3://{s3_bucket}/qc/report.html")
        url = mgr.presign(f"s3://{s3_bucket}/qc/report.html", expires_in=3600)
        assert url.startswith("https://")


def test_list_multiple_prefixes(s3_bucket):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
        mgr = S3FileManager(s3_bucket, region="us-east-1")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            p = f.name
        mgr.upload(p, f"s3://{s3_bucket}/runs/run1/output.txt")
        mgr.upload(p, f"s3://{s3_bucket}/runs/run2/output.txt")
        run1_objs = mgr.list(f"s3://{s3_bucket}/runs/run1/")
        run2_objs = mgr.list(f"s3://{s3_bucket}/runs/run2/")
        assert len(run1_objs) == 1
        assert len(run2_objs) == 1
