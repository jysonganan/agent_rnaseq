"""Salmon quasi-mapping quantification tool wrapper."""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.quantification.parsers import parse_salmon_meta_info


class SalmonQuantInput(BaseModel):
    fastq_r1: str
    fastq_r2: str | None = None
    index_path: str
    output_dir: str
    lib_type: str = "A"
    threads: int = Field(default=8, ge=1, le=256)
    extra_args: list[str] = Field(default_factory=list)


class SalmonQuantOutput(BaseModel):
    quant_sf_path: str
    lib_format_counts_path: str
    meta_info_path: str
    eq_classes_path: str | None = None
    inferred_lib_type: str
    mapping_rate: float
    tool_version: str | None = None


@tool_call
def run_salmon_quant(inp: SalmonQuantInput) -> SalmonQuantOutput:
    """Run Salmon quasi-mapping quantification.

    For paired-end input, passes ``-1``/``-2`` flags.
    For single-end input, passes ``-r``.
    """
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["salmon", "--version"], "salmon")

    cmd = [
        "salmon",
        "quant",
        "--index",
        inp.index_path,
        "--libType",
        inp.lib_type,
        "--output",
        inp.output_dir,
        "--threads",
        str(inp.threads),
    ]
    if inp.fastq_r2:
        cmd += ["-1", inp.fastq_r1, "-2", inp.fastq_r2]
    else:
        cmd += ["-r", inp.fastq_r1]
    cmd += inp.extra_args

    run_subprocess(cmd, tool_name="salmon")

    meta_info_path = os.path.join(inp.output_dir, "aux_info", "meta_info.json")
    with open(meta_info_path) as fh:
        meta = json.load(fh)
    parsed_meta = parse_salmon_meta_info(meta)

    quant_sf_path = os.path.join(inp.output_dir, "quant.sf")
    lib_format_counts_path = os.path.join(inp.output_dir, "lib_format_counts.json")
    eq_classes_path = os.path.join(inp.output_dir, "aux_info", "eq_classes.txt.gz")

    return SalmonQuantOutput(
        quant_sf_path=quant_sf_path,
        lib_format_counts_path=lib_format_counts_path,
        meta_info_path=meta_info_path,
        eq_classes_path=eq_classes_path if os.path.exists(eq_classes_path) else None,
        inferred_lib_type=parsed_meta["inferred_lib_type"],
        mapping_rate=parsed_meta["mapping_rate"],
        tool_version=version,
    )
