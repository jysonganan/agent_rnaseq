"""rMATS differential splicing analysis tool wrapper."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.splicing.parsers import count_rmats_significant, parse_rmats_summary

_EVENT_TYPES: list[str] = ["SE", "A5SS", "A3SS", "MXE", "RI"]


class RMATSInput(BaseModel):
    bam_list_b1: list[str] = Field(..., min_length=1)
    bam_list_b2: list[str] = Field(..., min_length=1)
    gtf_path: str
    output_dir: str
    read_length: int = Field(..., ge=1)
    paired_stats: bool = True
    novelSS: bool = False
    extra_args: list[str] = Field(default_factory=list)


class RMATSOutput(BaseModel):
    output_dir: str
    event_types: list[str]
    significant_events_count: dict[str, int]
    summary_path: str
    tool_version: str | None = None


def _read_event_counts(output_dir: str) -> dict[str, int]:
    """Read significant event counts from summary.txt or individual JC files.

    Tries ``{output_dir}/summary.txt`` first; falls back to counting
    significant rows in each ``{EventType}.MATS.JC.txt``.
    This function is a separate helper so tests can patch it directly.
    """
    summary_path = os.path.join(output_dir, "summary.txt")
    if os.path.exists(summary_path):
        with open(summary_path) as fh:
            return parse_rmats_summary(fh.read())

    counts: dict[str, int] = {}
    for event_type in _EVENT_TYPES:
        jc_path = os.path.join(output_dir, f"{event_type}.MATS.JC.txt")
        if os.path.exists(jc_path):
            with open(jc_path) as fh:
                counts[event_type] = count_rmats_significant(fh.read())
        else:
            counts[event_type] = 0
    return counts


@tool_call
def run_rmats(inp: RMATSInput) -> RMATSOutput:
    """Run rMATS differential splicing analysis.

    BAM lists are written to ``{output_dir}/b1.txt`` and ``b2.txt``
    and referenced via ``--b1``/``--b2``.  Significant event counts are
    read from ``summary.txt`` (if present) or from individual JC files.
    """
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["rmats.py", "--version"], "rMATS")

    b1_file = os.path.join(inp.output_dir, "b1.txt")
    b2_file = os.path.join(inp.output_dir, "b2.txt")
    with open(b1_file, "w") as fh:
        fh.write("\n".join(inp.bam_list_b1))
    with open(b2_file, "w") as fh:
        fh.write("\n".join(inp.bam_list_b2))

    cmd = [
        "rmats.py",
        "--b1",
        b1_file,
        "--b2",
        b2_file,
        "--gtf",
        inp.gtf_path,
        "--od",
        inp.output_dir,
        "--readLength",
        str(inp.read_length),
        "-t",
        "paired" if inp.paired_stats else "single",
    ]
    if inp.novelSS:
        cmd.append("--novelSS")
    cmd += inp.extra_args

    run_subprocess(cmd, tool_name="rMATS")

    significant_events_count = _read_event_counts(inp.output_dir)

    return RMATSOutput(
        output_dir=inp.output_dir,
        event_types=_EVENT_TYPES,
        significant_events_count=significant_events_count,
        summary_path=os.path.join(inp.output_dir, "summary.txt"),
        tool_version=version,
    )
