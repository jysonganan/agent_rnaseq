# TASK-13: AWS Integration (S3 + Batch)

## Goal
Implement AWS S3 file management and AWS Batch job submission/polling utilities used by tools and the Nextflow runner.

## Requirements
- `S3FileManager`: upload, download, list, presign, check existence. Uses `boto3`.
- `AWSBatchSubmitter`: `submit_aws_batch_job`, `poll_aws_batch_job` tool functions (per `tool_contracts.md`).
- All AWS credentials from environment variables or IAM roles only — never hardcoded.
- Presigned URL generation for artifact downloads (FastAPI artifact endpoint).
- S3 path normalization: `s3://bucket/key` ↔ local path resolution.
- Local dev fallback: when `AWS_ENDPOINT_URL` set, use LocalStack or MinIO.

## Files to Create
```
src/aws/
  __init__.py
  s3.py                # S3FileManager class
  batch.py             # AWSBatchSubmitter, submit_aws_batch_job, poll_aws_batch_job tool fns
  config.py            # AWS config from environment (region, bucket, queue, etc.)
tests/aws/
  __init__.py
  test_s3.py           # mocked with moto
  test_batch.py        # mocked with moto
```

## Files to Edit
- `src/config.py` — add AWS settings: `AWS_REGION`, `S3_BUCKET`, `BATCH_JOB_QUEUE`, `BATCH_JOB_DEFINITION`, `AWS_ENDPOINT_URL` (optional).
- `.env.example` — add AWS settings documentation.
- `src/tools/base.py` — `ToolExecutionError` already imported; no new deps.
- `pyproject.toml` — add boto3, moto (test) dependencies.

## Acceptance Criteria
- [ ] `S3FileManager.upload(local_path, s3_uri)` calls `boto3.client.upload_file` (mocked with moto).
- [ ] `S3FileManager.presign(s3_uri, expires_in)` returns a URL string.
- [ ] `S3FileManager.exists(s3_uri)` returns `True`/`False`.
- [ ] `submit_aws_batch_job` returns `BatchJobOutput` with `job_id`.
- [ ] `poll_aws_batch_job` returns `BatchPollOutput.status` matching mocked Batch response.
- [ ] No AWS credentials appear in log output (tested with logging capture).
- [ ] `S3FileManager` raises `ValueError` if `s3_uri` does not start with `s3://`.

## Definition of Done
`pytest tests/aws/` green using moto mocks. No real AWS calls made.
