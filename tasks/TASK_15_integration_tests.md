# TASK-15: Integration Tests & End-to-End Test Suite

## Goal
Implement integration tests that exercise the full pipeline stack from API request through agent routing to tool execution and DB persistence, using mocked external tools and a real in-memory SQLite DB.

## Requirements
- Integration test suite: `tests/integration/`.
- Fixtures: small synthetic FASTQ files (or mocked tool outputs) to exercise each pipeline stage.
- End-to-end test: `POST /runs` → agent routing → all stages complete → `GET /runs/{id}` shows `completed`.
- AWS tests: LocalStack or moto mocks for all S3/Batch calls.
- scRNA-seq integration test using PBMC 3k fixture or mocked CellRanger output.
- CI-ready: all integration tests run in Docker Compose environment.

## Files to Create
```
tests/integration/
  __init__.py
  conftest.py          # Docker Compose fixtures, in-memory DB, tool mocks
  test_bulk_rnaseq_pipeline.py   # Full bulk RNA-seq run: QC → alignment → quant → DE → GSEA
  test_scrna_pipeline.py         # scRNA-seq run: CellRanger → Scanpy
  test_variant_pipeline.py       # Alignment → GATK → VCF output
  test_api_run_lifecycle.py      # POST /runs, poll status, GET results
  test_agent_routing.py          # Routing correctness for various stage combinations
  test_aws_pipeline.py           # S3 input/output with moto mocks
  fixtures/
    synthetic_R1.fastq.gz        # Tiny synthetic FASTQ (100 reads)
    synthetic_R2.fastq.gz
    mock_star_output/
    mock_deseq2_output/
    mock_cellranger_output/
```

## Files to Edit
- `Makefile` — add `test-integration` target.
- `.github/workflows/ci.yml` — add integration test job (if CI configured).

## Acceptance Criteria
- [ ] `test_bulk_rnaseq_pipeline.py` completes with `AnalysisRun.status == completed`.
- [ ] `test_bulk_rnaseq_pipeline.py` verifies `DEGResult` rows written to DB.
- [ ] `test_bulk_rnaseq_pipeline.py` verifies `GSEAResult` rows written to DB.
- [ ] `test_api_run_lifecycle.py` verifies `/runs/{id}` transitions from `pending` → `running` → `completed`.
- [ ] `test_agent_routing.py` verifies stages not in `run_config.stages` are skipped.
- [ ] `test_aws_pipeline.py` verifies S3 upload called for each artifact (moto).
- [ ] `test_scrna_pipeline.py` verifies `CellRangerCountOutput.summary_stats` stored in DB.
- [ ] All integration tests pass in under 60 seconds (mocked tools, no real binaries).
- [ ] Zero real subprocess calls to bioinformatics tools (all mocked).

## Definition of Done
`make test-integration` green. All tests pass in CI Docker environment.
