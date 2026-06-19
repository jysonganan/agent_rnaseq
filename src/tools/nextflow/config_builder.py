"""Generates nextflow.config override content from RunConfig execution settings."""

from __future__ import annotations


def build_config_overrides(execution_config: dict) -> str:
    """Return a nextflow.config snippet that overrides executor, cpus, and memory.

    Args:
        execution_config: dict with keys ``executor`` (str), ``cpus`` (int),
            ``memory_gb`` (int), and optionally ``aws_batch_queue`` (str),
            ``s3_work_dir`` (str), ``aws_region`` (str).

    Returns:
        Nextflow config string that can be written to a file or appended to
        nextflow.config before a run.
    """
    executor = execution_config.get("executor", "local")
    cpus = int(execution_config.get("cpus", 4))
    memory_gb = int(execution_config.get("memory_gb", 16))

    if executor == "aws_batch":
        queue = execution_config.get("aws_batch_queue", "")
        s3_work = execution_config.get("s3_work_dir", "s3://nextflow-work/")
        region = execution_config.get("aws_region", "us-east-1")
        return f"""\
process {{
    executor = 'awsbatch'
    cpus = {cpus}
    memory = '{memory_gb} GB'
    queue = '{queue}'
}}
aws {{
    region = '{region}'
}}
workDir = '{s3_work}'
"""
    # local / nextflow executor
    return f"""\
process {{
    executor = 'local'
    cpus = {cpus}
    memory = '{memory_gb} GB'
}}
workDir = '/tmp/nextflow_work'
"""


def build_params(
    *,
    output_dir: str,
    genome_dir: str | None = None,
    gtf_path: str | None = None,
    fastq_r1: str | None = None,
    fastq_r2: str | None = None,
    sample_id: str | None = None,
    **extra: object,
) -> dict:
    """Build a Nextflow params dict from common RNA-seq run fields.

    Only non-None values are included.  Callers may pass additional keyword
    arguments via ``extra`` which are merged in verbatim.
    """
    params: dict = {"output_dir": output_dir}
    for key, value in [
        ("genome_dir", genome_dir),
        ("gtf_path", gtf_path),
        ("fastq_r1", fastq_r1),
        ("fastq_r2", fastq_r2),
        ("sample_id", sample_id),
    ]:
        if value is not None:
            params[key] = value
    params.update(extra)
    return params
