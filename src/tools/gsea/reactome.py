"""Reactome GSEA tool wrapper (R subprocess via fgsea)."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.gsea.parsers import (
    count_significant_pathways,
    parse_gsea_results,
)


class ReactomeGSEAInput(BaseModel):
    de_results_path: str
    contrast_name: str
    output_dir: str
    organism: Literal["human", "mouse"] = "human"
    rank_metric: Literal["stat", "log2fc_signed"] = "stat"
    nperm: int = Field(default=1000, ge=100, le=10000)
    r_script_path: str


class ReactomeGSEAOutput(BaseModel):
    results_path: str
    enrichment_plots_dir: str
    significant_pathway_count: int
    tool_version: str | None = None


def _count_significant_gsea(
    results_path: str,
    padj_threshold: float = 0.05,
) -> int:
    """Read a GSEA results CSV and count significant pathways (patchable in tests)."""
    try:
        with open(results_path) as fh:
            results = parse_gsea_results(fh.read())
        return count_significant_pathways(results, padj_threshold)
    except OSError:
        return 0


@tool_call
def run_reactome_gsea(inp: ReactomeGSEAInput) -> ReactomeGSEAOutput:
    """Run Reactome GSEA via a validated R subprocess (fgsea).

    The R script is called with positional CLI arguments — R code is never
    constructed via string interpolation, satisfying the safety policy.
    """
    os.makedirs(inp.output_dir, exist_ok=True)

    version = detect_version(["Rscript", "--version"], "reactome_gsea")

    cmd = [
        "Rscript",
        "--vanilla",
        inp.r_script_path,
        inp.de_results_path,
        inp.organism,
        inp.output_dir,
        inp.rank_metric,
        str(inp.nperm),
    ]
    run_subprocess(cmd, tool_name="reactome_gsea")

    results_path = os.path.join(inp.output_dir, "gsea_results.csv")
    plots_dir = os.path.join(inp.output_dir, "plots")
    sig_count = _count_significant_gsea(results_path)

    return ReactomeGSEAOutput(
        results_path=results_path,
        enrichment_plots_dir=plots_dir,
        significant_pathway_count=sig_count,
        tool_version=version,
    )
