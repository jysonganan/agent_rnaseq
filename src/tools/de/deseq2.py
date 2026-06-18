"""DESeq2 differential expression tool wrapper (R subprocess)."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.de.parsers import (
    DEContrastSummary,
    compute_contrast_summary,
    parse_deseq2_results,
)


class DEContrast(BaseModel):
    name: str
    numerator: str
    denominator: str


class DESeq2Input(BaseModel):
    counts_matrix_path: str
    sample_metadata_path: str
    contrasts: list[DEContrast] = Field(..., min_length=1)
    output_dir: str
    min_count: int = Field(default=10, ge=1, le=1000)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)
    lfc_threshold: float = Field(default=0.0, ge=0.0, le=5.0)
    r_script_path: str


class DESeq2Output(BaseModel):
    results_paths: dict[str, str]
    normalized_counts_path: str
    size_factors_path: str
    dispersion_plot_path: str
    pca_plot_path: str
    contrast_summaries: dict[str, DEContrastSummary]
    tool_version: str | None = None


def _read_contrast_summary(
    results_path: str,
    alpha: float,
) -> DEContrastSummary:
    """Read a DESeq2 results CSV and return its contrast summary (patchable in tests)."""
    try:
        with open(results_path) as fh:
            results = parse_deseq2_results(fh.read())
        return compute_contrast_summary(results, alpha)
    except OSError:
        return DEContrastSummary(
            total_genes=0, upregulated=0, downregulated=0, not_significant=0
        )


@tool_call
def run_deseq2(inp: DESeq2Input) -> DESeq2Output:
    """Run DESeq2 differential expression via a validated R subprocess.

    The R script is called with positional CLI arguments — R code is never
    constructed via string interpolation, satisfying the safety policy.
    One subprocess call is made per contrast.
    """
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["Rscript", "--version"], "DESeq2")

    results_paths: dict[str, str] = {}
    contrast_summaries: dict[str, DEContrastSummary] = {}

    for contrast in inp.contrasts:
        cmd = [
            "Rscript",
            "--vanilla",
            inp.r_script_path,
            inp.counts_matrix_path,
            inp.sample_metadata_path,
            contrast.name,
            contrast.numerator,
            contrast.denominator,
            inp.output_dir,
            str(inp.alpha),
            str(inp.lfc_threshold),
            str(inp.min_count),
        ]
        run_subprocess(cmd, tool_name="DESeq2")

        results_path = os.path.join(inp.output_dir, f"{contrast.name}_results.csv")
        results_paths[contrast.name] = results_path
        contrast_summaries[contrast.name] = _read_contrast_summary(results_path, inp.alpha)

    return DESeq2Output(
        results_paths=results_paths,
        normalized_counts_path=os.path.join(inp.output_dir, "normalized_counts.csv"),
        size_factors_path=os.path.join(inp.output_dir, "size_factors.csv"),
        dispersion_plot_path=os.path.join(inp.output_dir, "dispersion_plot.pdf"),
        pca_plot_path=os.path.join(inp.output_dir, "pca_plot.pdf"),
        contrast_summaries=contrast_summaries,
        tool_version=version,
    )
