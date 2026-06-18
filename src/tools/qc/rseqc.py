from __future__ import annotations

import os

from pydantic import BaseModel, Field, field_validator

from src.tools.base import (
    ToolValidationError,
    detect_version,
    run_subprocess,
    tool_call,
)
from src.tools.qc.parsers import parse_rseqc_infer_experiment, parse_rseqc_read_distribution

_VALID_MODULES = frozenset(["read_distribution", "infer_experiment", "junction_saturation"])

_MODULE_SCRIPT: dict[str, str] = {
    "read_distribution": "read_distribution.py",
    "infer_experiment": "infer_experiment.py",
    "junction_saturation": "junction_saturation.py",
}


class RSeQCInput(BaseModel):
    bam_path: str
    bam_index_path: str
    bed_annotation_path: str
    output_prefix: str
    modules: list[str] = Field(
        default=["read_distribution", "infer_experiment", "junction_saturation"]
    )

    @field_validator("modules")
    @classmethod
    def _valid_modules(cls, v: list[str]) -> list[str]:
        invalid = set(v) - _VALID_MODULES
        if invalid:
            raise ValueError(f"Unknown RSeQC modules: {invalid}. Valid: {_VALID_MODULES}")
        return v


class RSeQCOutput(BaseModel):
    module_outputs: dict[str, str]
    read_distribution: dict  # type: ignore[type-arg]
    infer_experiment_result: dict  # type: ignore[type-arg]
    tool_version: str | None = None


@tool_call
def run_rseqc(inp: RSeQCInput) -> RSeQCOutput:
    """Run selected RSeQC post-alignment QC modules."""
    if not inp.modules:
        raise ToolValidationError("rseqc", "modules", "must specify at least one module")

    version = detect_version([_MODULE_SCRIPT["read_distribution"], "--version"], "rseqc")

    module_outputs: dict[str, str] = {}
    read_distribution: dict = {}  # type: ignore[type-arg]
    infer_experiment_result: dict = {}  # type: ignore[type-arg]

    out_dir = os.path.dirname(inp.output_prefix) or "."
    os.makedirs(out_dir, exist_ok=True)

    for module in inp.modules:
        script = _MODULE_SCRIPT[module]
        out_file = f"{inp.output_prefix}_{module}.txt"

        if module == "read_distribution":
            cmd = [script, "-i", inp.bam_path, "-r", inp.bed_annotation_path]
            proc = run_subprocess(cmd, tool_name="rseqc")
            stdout = proc.stdout.decode("utf-8", errors="replace")
            with open(out_file, "w") as fh:
                fh.write(stdout)
            read_distribution = parse_rseqc_read_distribution(stdout)

        elif module == "infer_experiment":
            cmd = [script, "-i", inp.bam_path, "-r", inp.bed_annotation_path]
            proc = run_subprocess(cmd, tool_name="rseqc")
            stdout = proc.stdout.decode("utf-8", errors="replace")
            with open(out_file, "w") as fh:
                fh.write(stdout)
            infer_experiment_result = parse_rseqc_infer_experiment(stdout)

        elif module == "junction_saturation":
            cmd = [
                script,
                "-i",
                inp.bam_path,
                "-r",
                inp.bed_annotation_path,
                "-o",
                inp.output_prefix,
            ]
            run_subprocess(cmd, tool_name="rseqc")
            # junction_saturation writes its own files; record prefix
            out_file = inp.output_prefix

        module_outputs[module] = out_file

    return RSeQCOutput(
        module_outputs=module_outputs,
        read_distribution=read_distribution,
        infer_experiment_result=infer_experiment_result,
        tool_version=version,
    )
