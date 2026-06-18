from __future__ import annotations

import os
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from src.tools.base import (
    ToolValidationError,
    detect_version,
    run_subprocess,
    tool_call,
)
from src.tools.qc.parsers import parse_fastqc_summary


class FastQCInput(BaseModel):
    fastq_paths: list[str] = Field(..., min_length=1)
    output_dir: str
    threads: int = Field(default=4, ge=1, le=256)

    @field_validator("fastq_paths")
    @classmethod
    def _max_two_files(cls, v: list[str]) -> list[str]:
        if len(v) > 2:
            raise ValueError("fastq_paths may contain at most 2 files (R1 + R2)")
        return v


class FastQCOutput(BaseModel):
    report_html_paths: list[str]
    report_zip_paths: list[str]
    summary: dict[str, str]
    tool_version: str | None = None


def _sample_stem(fastq_path: str) -> str:
    """Derive the FastQC output stem from a FASTQ filename."""
    name = Path(fastq_path).name
    for suffix in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def _read_zip_summary(zip_path: str) -> dict[str, str]:
    """Open a FastQC ZIP and parse the embedded summary.txt."""
    with zipfile.ZipFile(zip_path) as zf:
        # summary.txt is at <stem>_fastqc/summary.txt
        candidates = [n for n in zf.namelist() if n.endswith("summary.txt")]
        if not candidates:
            return {}
        with zf.open(candidates[0]) as fh:
            text = fh.read().decode("utf-8", errors="replace")
    return parse_fastqc_summary(text)


@tool_call
def run_fastqc(inp: FastQCInput) -> FastQCOutput:
    """Run FastQC on one or two FASTQ files."""
    if not inp.fastq_paths:
        raise ToolValidationError("fastqc", "fastq_paths", "must not be empty")

    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["fastqc", "--version"], "fastqc")

    cmd = [
        "fastqc",
        *inp.fastq_paths,
        "--outdir",
        inp.output_dir,
        "--threads",
        str(inp.threads),
    ]
    run_subprocess(cmd, tool_name="fastqc")

    # Discover output files
    stems = [_sample_stem(p) for p in inp.fastq_paths]
    html_paths = [os.path.join(inp.output_dir, f"{s}_fastqc.html") for s in stems]
    zip_paths = [os.path.join(inp.output_dir, f"{s}_fastqc.zip") for s in stems]

    # Parse summary from first available ZIP
    summary: dict[str, str] = {}
    for zp in zip_paths:
        if os.path.exists(zp):
            summary = _read_zip_summary(zp)
            break

    return FastQCOutput(
        report_html_paths=html_paths,
        report_zip_paths=zip_paths,
        summary=summary,
        tool_version=version,
    )
