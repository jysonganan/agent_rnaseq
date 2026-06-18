"""RSEM gene/isoform quantification tool wrapper."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call


class RSEMInput(BaseModel):
    bam_path: str
    rsem_reference: str
    output_prefix: str
    paired_end: bool = True
    threads: int = Field(default=8, ge=1, le=256)
    extra_args: list[str] = Field(default_factory=list)


class RSEMOutput(BaseModel):
    genes_results_path: str
    isoforms_results_path: str
    stat_dir: str
    tool_version: str | None = None


@tool_call
def run_rsem(inp: RSEMInput) -> RSEMOutput:
    """Run rsem-calculate-expression on a transcriptome-aligned BAM."""
    output_dir = str(Path(inp.output_prefix).parent)
    os.makedirs(output_dir, exist_ok=True)

    version = detect_version(["rsem-calculate-expression", "--version"], "rsem")

    cmd = ["rsem-calculate-expression", "--bam", "--num-threads", str(inp.threads)]
    if inp.paired_end:
        cmd.append("--paired-end")
    cmd += inp.extra_args
    cmd += [inp.bam_path, inp.rsem_reference, inp.output_prefix]

    run_subprocess(cmd, tool_name="rsem-calculate-expression")

    return RSEMOutput(
        genes_results_path=f"{inp.output_prefix}.genes.results",
        isoforms_results_path=f"{inp.output_prefix}.isoforms.results",
        stat_dir=f"{inp.output_prefix}.stat",
        tool_version=version,
    )
