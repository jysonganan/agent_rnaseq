"""CellRanger count tool wrapper."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.scrna.parsers import parse_web_summary


class CellRangerCountInput(BaseModel):
    fastq_dirs: list[str] = Field(..., min_length=1)
    sample_name: str
    transcriptome_path: str
    output_dir: str
    expected_cells: int | None = None
    localcores: int = Field(default=8, ge=1, le=256)
    localmem: int = Field(default=64, ge=1, le=512)


class CellRangerCountOutput(BaseModel):
    output_dir: str
    filtered_matrix_dir: str
    molecule_info_path: str
    summary_html_path: str
    summary_stats: dict  # type: ignore[type-arg]
    tool_version: str | None = None


def _read_summary_stats(outs_dir: str) -> dict:  # type: ignore[type-arg]
    """Read CellRanger metrics_summary.csv and return parsed stats (patchable in tests)."""
    csv_path = os.path.join(outs_dir, "metrics_summary.csv")
    try:
        with open(csv_path) as fh:
            return parse_web_summary(fh.read())
    except OSError:
        return {}


@tool_call
def run_cellranger_count(inp: CellRangerCountInput) -> CellRangerCountOutput:
    """Run CellRanger count on one or more FASTQ directories.

    CellRanger creates ``{output_dir}/{sample_name}/outs/`` containing the
    filtered matrix, molecule info, and web summary.  Multiple FASTQ directories
    are passed as a comma-separated list to ``--fastqs``.
    """
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["cellranger", "--version"], "cellranger")

    fastqs_arg = ",".join(inp.fastq_dirs)

    cmd = [
        "cellranger",
        "count",
        f"--id={inp.sample_name}",
        f"--fastqs={fastqs_arg}",
        f"--transcriptome={inp.transcriptome_path}",
        f"--localcores={inp.localcores}",
        f"--localmem={inp.localmem}",
    ]
    if inp.expected_cells is not None:
        cmd.append(f"--expect-cells={inp.expected_cells}")

    run_subprocess(cmd, tool_name="cellranger", cwd=inp.output_dir)

    outs_dir = os.path.join(inp.output_dir, inp.sample_name, "outs")
    summary_stats = _read_summary_stats(outs_dir)

    return CellRangerCountOutput(
        output_dir=inp.output_dir,
        filtered_matrix_dir=os.path.join(outs_dir, "filtered_feature_bc_matrix"),
        molecule_info_path=os.path.join(outs_dir, "molecule_info.h5"),
        summary_html_path=os.path.join(outs_dir, "web_summary.html"),
        summary_stats=summary_stats,
        tool_version=version,
    )
