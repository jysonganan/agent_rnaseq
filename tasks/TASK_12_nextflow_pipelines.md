# TASK-12: Nextflow Pipeline Definitions

## Goal
Implement Nextflow DSL2 workflow definitions for compute-heavy pipeline phases, supporting both local and AWS Batch executors transparently.

## Requirements
- Nextflow DSL2 workflows for: QC, alignment, quantification, variant calling.
- `nextflow.config` with profiles: `local`, `awsbatch`.
- AWS Batch profile: sets `process.executor = 'awsbatch'`, queue, container registry.
- Local profile: sets `process.executor = 'local'`, CPU/memory limits.
- Python `NextflowRunner` class that submits Nextflow jobs and polls for completion.
- All process containers pin tool versions (no `latest` tags).
- Work directory: local temp dir or S3 bucket depending on profile.

## Files to Create
```
nextflow/
  main.nf              # Top-level workflow entry
  nextflow.config      # profiles: local, awsbatch
  modules/
    fastqc.nf
    star.nf
    samtools.nf
    htseq.nf
    salmon.nf
    rsem.nf
    gatk.nf
    rmats.nf
  workflows/
    qc.nf
    alignment.nf
    quantification.nf
    variant_calling.nf
src/tools/nextflow/
  __init__.py
  runner.py            # NextflowRunner: submit, poll, cancel
  config_builder.py    # Generates nextflow.config overrides from RunConfig
tests/tools/
  test_nextflow_runner.py
```

## Files to Edit
- `src/tools/base.py` — add `ExecutionBackend` enum: `local`, `nextflow`, `aws_batch`.
- `docker-compose.yml` — add Nextflow service for local dev.

## Acceptance Criteria
- [ ] `nextflow run nextflow/main.nf -profile local --help` exits 0 (dry syntax check).
- [ ] `NextflowRunner.submit(config)` calls `nextflow run` with correct args (mocked subprocess).
- [ ] `NextflowRunner.poll(run_id)` returns correct status from mocked Nextflow log.
- [ ] `config_builder.py` generates correct `awsbatch` executor config from `RunConfig.execution`.
- [ ] All Nextflow modules specify container with pinned version tag.
- [ ] `process.memory` and `process.cpus` directives set per module.

## Definition of Done
`nextflow -version` check passes. `pytest tests/tools/test_nextflow_runner.py` green.
