"""Tests for S3FileManager — mocked with moto."""

from __future__ import annotations

import logging

import boto3
import pytest
from moto import mock_aws

from src.aws.s3 import S3FileManager

BUCKET = "test-rnaseq-bucket"
REGION = "us-east-1"


@pytest.fixture
def s3_setup():
    """Yield an (S3FileManager, boto3 s3 client) pair inside a moto mock."""
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        manager = S3FileManager(BUCKET, region=REGION)
        yield manager, client


# ── upload ─────────────────────────────────────────────────────────────────────


def test_upload_creates_object(s3_setup, tmp_path):
    manager, client = s3_setup
    f = tmp_path / "sample.fastq.gz"
    f.write_bytes(b"@SEQ_001\nACGT\n+\nIIII\n")
    manager.upload(str(f), f"s3://{BUCKET}/uploads/sample.fastq.gz")
    # Verify the object exists via the raw client
    resp = client.get_object(Bucket=BUCKET, Key="uploads/sample.fastq.gz")
    assert resp["Body"].read() == f.read_bytes()


def test_upload_raises_for_invalid_uri(s3_setup, tmp_path):
    manager, _ = s3_setup
    f = tmp_path / "x.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="s3://"):
        manager.upload(str(f), "not-an-s3-uri/bucket/key")


# ── exists ────────────────────────────────────────────────────────────────────


def test_exists_true_after_upload(s3_setup, tmp_path):
    manager, _ = s3_setup
    f = tmp_path / "a.txt"
    f.write_text("hello")
    manager.upload(str(f), f"s3://{BUCKET}/a.txt")
    assert manager.exists(f"s3://{BUCKET}/a.txt") is True


def test_exists_false_for_missing(s3_setup):
    manager, _ = s3_setup
    assert manager.exists(f"s3://{BUCKET}/does-not-exist.txt") is False


def test_exists_raises_for_invalid_uri(s3_setup):
    manager, _ = s3_setup
    with pytest.raises(ValueError, match="s3://"):
        manager.exists("bad-uri")


# ── download ──────────────────────────────────────────────────────────────────


def test_download_content_matches(s3_setup, tmp_path):
    manager, client = s3_setup
    content = b"alignment output\n"
    client.put_object(Bucket=BUCKET, Key="results/out.bam", Body=content)
    dest = tmp_path / "out.bam"
    manager.download(f"s3://{BUCKET}/results/out.bam", str(dest))
    assert dest.read_bytes() == content


def test_download_creates_parent_dirs(s3_setup, tmp_path):
    manager, client = s3_setup
    client.put_object(Bucket=BUCKET, Key="deep/nested/file.txt", Body=b"data")
    dest = tmp_path / "deep" / "nested" / "file.txt"
    manager.download(f"s3://{BUCKET}/deep/nested/file.txt", str(dest))
    assert dest.exists()


# ── list ──────────────────────────────────────────────────────────────────────


def test_list_returns_all_keys_under_prefix(s3_setup, client_=None):
    manager, client = s3_setup
    for key in ["results/a.txt", "results/b.txt", "other/c.txt"]:
        client.put_object(Bucket=BUCKET, Key=key, Body=b"x")
    uris = manager.list(f"s3://{BUCKET}/results/")
    assert set(uris) == {
        f"s3://{BUCKET}/results/a.txt",
        f"s3://{BUCKET}/results/b.txt",
    }


def test_list_returns_empty_for_missing_prefix(s3_setup):
    manager, _ = s3_setup
    assert manager.list(f"s3://{BUCKET}/no-such-prefix/") == []


# ── presign ───────────────────────────────────────────────────────────────────


def test_presign_returns_nonempty_url(s3_setup, tmp_path):
    manager, client = s3_setup
    client.put_object(Bucket=BUCKET, Key="artifact.html", Body=b"<html/>")
    url = manager.presign(f"s3://{BUCKET}/artifact.html", expires_in=300)
    assert isinstance(url, str)
    assert url.startswith("https://") or url.startswith("http://")
    assert "artifact.html" in url


def test_presign_raises_for_invalid_uri(s3_setup):
    manager, _ = s3_setup
    with pytest.raises(ValueError, match="s3://"):
        manager.presign("not-s3://bucket/key")


# ── no credentials in logs ────────────────────────────────────────────────────


def test_no_credentials_in_log_output(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKECREDENTIAL99")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "supersecretfakekey0000000000000000000000")
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        manager = S3FileManager(BUCKET, region=REGION)
        f = tmp_path / "test.txt"
        f.write_text("data")
        with caplog.at_level(logging.DEBUG, logger="src.aws.s3"):
            manager.upload(str(f), f"s3://{BUCKET}/test.txt")
            manager.exists(f"s3://{BUCKET}/test.txt")
        assert "AKIAFAKECREDENTIAL99" not in caplog.text
        assert "supersecretfakekey0000000000000000000000" not in caplog.text
