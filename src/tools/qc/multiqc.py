from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.qc.parsers import parse_multiqc_general_stats

_GENERAL_STATS_FILE = "multiqc_general_stats.json"


class MultiQCInput(BaseModel):
    input_dirs: list[str] = Field(..., min_length=1)
    output_dir: str
    report_name: str = "multiqc_report"


class MultiQCOutput(BaseModel):
    report_html_path: str
    data_dir: str
    parsed_metrics: dict  # type: ignore[type-arg]
    tool_version: str | None = None


@tool_call
def run_multiqc(inp: MultiQCInput) -> MultiQCOutput:
    """Aggregate QC reports with MultiQC."""
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["multiqc", "--version"], "multiqc")

    cmd = [
        "multiqc",
        *inp.input_dirs,
        "--outdir",
        inp.output_dir,
        "--filename",
        inp.report_name,
        "--force",
    ]
    run_subprocess(cmd, tool_name="multiqc")

    report_html = os.path.join(inp.output_dir, f"{inp.report_name}.html")
    data_dir = os.path.join(inp.output_dir, f"{inp.report_name}_data")

    # Parse general stats
    parsed_metrics: dict = {}  # type: ignore[type-arg]
    stats_path = os.path.join(data_dir, _GENERAL_STATS_FILE)
    if os.path.exists(stats_path):
        with open(stats_path) as fh:
            raw = json.load(fh)
        parsed_metrics = parse_multiqc_general_stats(raw)

    return MultiQCOutput(
        report_html_path=report_html,
        data_dir=data_dir,
        parsed_metrics=parsed_metrics,
        tool_version=version,
    )
