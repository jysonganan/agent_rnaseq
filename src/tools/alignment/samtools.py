"""samtools sort / index / flagstat tool wrapper."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from src.tools.alignment.parsers import parse_samtools_flagstat
from src.tools.base import detect_version, run_subprocess, tool_call


class SamtoolsInput(BaseModel):
    bam_path: str
    output_prefix: str
    threads: int = Field(default=4, ge=1, le=256)


class SamtoolsOutput(BaseModel):
    sorted_bam_path: str
    bai_path: str
    flagstat: dict  # type: ignore[type-arg]
    tool_version: str | None = None


@tool_call
def run_samtools_sort_index(inp: SamtoolsInput) -> SamtoolsOutput:
    """Sort and index a BAM, then capture flagstat metrics."""
    output_dir = str(Path(inp.output_prefix).parent)
    os.makedirs(output_dir, exist_ok=True)

    version = detect_version(["samtools", "--version"], "samtools")

    sorted_bam = f"{inp.output_prefix}.sorted.bam"
    bai_path = f"{sorted_bam}.bai"

    run_subprocess(
        ["samtools", "sort", "-@", str(inp.threads), "-o", sorted_bam, inp.bam_path],
        tool_name="samtools",
    )

    run_subprocess(
        ["samtools", "index", "-@", str(inp.threads), sorted_bam],
        tool_name="samtools",
    )

    flagstat_proc = run_subprocess(
        ["samtools", "flagstat", sorted_bam],
        tool_name="samtools",
    )
    flagstat = parse_samtools_flagstat(flagstat_proc.stdout.decode("utf-8", errors="replace"))

    return SamtoolsOutput(
        sorted_bam_path=sorted_bam,
        bai_path=bai_path,
        flagstat=flagstat,
        tool_version=version,
    )
