"""HTSeq-count tool wrapper."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.quantification.parsers import parse_htseq_counts


class HTSeqInput(BaseModel):
    bam_path: str
    gtf_path: str
    output_path: str
    stranded: Literal["yes", "no", "reverse"] = "reverse"
    mode: Literal["union", "intersection-strict", "intersection-nonempty"] = "union"
    additional_args: list[str] = Field(default_factory=list)


class HTSeqOutput(BaseModel):
    counts_path: str
    total_reads: int
    counted_reads: int
    no_feature_reads: int
    ambiguous_reads: int
    tool_version: str | None = None


@tool_call
def run_htseq_count(inp: HTSeqInput) -> HTSeqOutput:
    """Run htseq-count on a BAM file and parse summary statistics.

    Counts are written to ``inp.output_path``; stats are derived from the
    special ``__`` category lines that htseq-count appends to stdout.
    """
    output_dir = str(Path(inp.output_path).parent)
    os.makedirs(output_dir, exist_ok=True)

    version = detect_version(["htseq-count", "--version"], "htseq-count")

    cmd = [
        "htseq-count",
        "--format",
        "bam",
        "--stranded",
        inp.stranded,
        "--mode",
        inp.mode,
        *inp.additional_args,
        inp.bam_path,
        inp.gtf_path,
    ]
    proc = run_subprocess(cmd, tool_name="htseq-count")
    content = proc.stdout.decode("utf-8", errors="replace")

    with open(inp.output_path, "w") as fh:
        fh.write(content)

    stats = parse_htseq_counts(content)

    return HTSeqOutput(
        counts_path=inp.output_path,
        total_reads=stats["total_reads"],
        counted_reads=stats["counted_reads"],
        no_feature_reads=stats["no_feature_reads"],
        ambiguous_reads=stats["ambiguous_reads"],
        tool_version=version,
    )
