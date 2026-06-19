"""GATK HaplotypeCaller and VariantFiltration tool wrappers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.tools.base import detect_version, run_subprocess, tool_call
from src.tools.variant.parsers import parse_vcf_variant_counts


class GATKHaplotypeCallerInput(BaseModel):
    bam_path: str
    bam_index_path: str
    reference_fasta: str
    output_vcf_path: str
    dbsnp_path: str | None = None
    interval_list: str | None = None
    emit_ref_confidence: Literal["NONE", "BP_RESOLUTION", "GVCF"] = "NONE"
    extra_args: list[str] = Field(default_factory=list)


class GATKHaplotypeCallerOutput(BaseModel):
    vcf_path: str
    vcf_index_path: str
    variant_count: int
    tool_version: str | None = None


class GATKVariantFilterInput(BaseModel):
    vcf_path: str
    reference_fasta: str
    output_vcf_path: str
    snp_filter_expression: str
    indel_filter_expression: str


class GATKVariantFilterOutput(BaseModel):
    filtered_vcf_path: str
    filtered_vcf_index_path: str
    pass_variant_count: int
    filtered_variant_count: int
    tool_version: str | None = None


def _count_vcf_variants(vcf_path: str) -> dict:  # type: ignore[type-arg]
    """Open a VCF and return parsed variant counts (patchable in tests)."""
    try:
        with open(vcf_path) as fh:
            return parse_vcf_variant_counts(fh.read())
    except OSError:
        return {"total_count": 0, "pass_count": 0, "filtered_count": 0}


@tool_call
def run_gatk_haplotypecaller(inp: GATKHaplotypeCallerInput) -> GATKHaplotypeCallerOutput:
    """Run GATK HaplotypeCaller on a BAM file."""
    output_dir = str(Path(inp.output_vcf_path).parent)
    os.makedirs(output_dir, exist_ok=True)

    version = detect_version(["gatk", "--version"], "gatk")

    cmd = [
        "gatk",
        "HaplotypeCaller",
        "-R",
        inp.reference_fasta,
        "-I",
        inp.bam_path,
        "-O",
        inp.output_vcf_path,
    ]
    if inp.dbsnp_path:
        cmd += ["--dbsnp", inp.dbsnp_path]
    if inp.interval_list:
        cmd += ["-L", inp.interval_list]
    if inp.emit_ref_confidence != "NONE":
        cmd += ["--emit-ref-confidence", inp.emit_ref_confidence]
    cmd += inp.extra_args

    run_subprocess(cmd, tool_name="gatk")

    counts = _count_vcf_variants(inp.output_vcf_path)

    return GATKHaplotypeCallerOutput(
        vcf_path=inp.output_vcf_path,
        vcf_index_path=f"{inp.output_vcf_path}.tbi",
        variant_count=counts["total_count"],
        tool_version=version,
    )


@tool_call
def run_gatk_variant_filter(inp: GATKVariantFilterInput) -> GATKVariantFilterOutput:
    """Apply hard filters to a VCF using GATK VariantFiltration."""
    output_dir = str(Path(inp.output_vcf_path).parent)
    os.makedirs(output_dir, exist_ok=True)

    version = detect_version(["gatk", "--version"], "gatk")

    cmd = [
        "gatk",
        "VariantFiltration",
        "-R",
        inp.reference_fasta,
        "-V",
        inp.vcf_path,
        "-O",
        inp.output_vcf_path,
        "--filter-expression",
        inp.snp_filter_expression,
        "--filter-name",
        "SNPFilter",
        "--filter-expression",
        inp.indel_filter_expression,
        "--filter-name",
        "IndelFilter",
    ]

    run_subprocess(cmd, tool_name="gatk")

    counts = _count_vcf_variants(inp.output_vcf_path)

    return GATKVariantFilterOutput(
        filtered_vcf_path=inp.output_vcf_path,
        filtered_vcf_index_path=f"{inp.output_vcf_path}.tbi",
        pass_variant_count=counts["pass_count"],
        filtered_variant_count=counts["filtered_count"],
        tool_version=version,
    )
