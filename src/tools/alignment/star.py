"""STAR aligner tool wrapper."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.tools.alignment.parsers import parse_star_log_final
from src.tools.base import detect_version, run_subprocess, tool_call


class STARAlignInput(BaseModel):
    fastq_r1: str
    fastq_r2: str | None = None
    genome_dir: str
    output_prefix: str
    run_mode: Literal["alignReads"] = "alignReads"
    threads: int = Field(default=8, ge=1, le=256)
    extra_args: list[str] = Field(default_factory=list)
    quantification_mode: Literal["None", "TranscriptomeSAM", "GeneCounts"] = "GeneCounts"
    out_sam_type: str = "BAM SortedByCoordinate"
    alignment_mode: Literal["genome", "transcriptome", "both"] = "genome"


class STARAlignOutput(BaseModel):
    bam_path: str
    bam_index_path: str
    log_final_path: str
    splice_junctions_path: str
    gene_counts_path: str | None = None
    transcriptome_bam_path: str | None = None
    alignment_stats: dict  # type: ignore[type-arg]
    tool_version: str | None = None


def _build_star_cmd(
    inp: STARAlignInput,
    output_prefix: str,
    quant_mode: str,
) -> list[str]:
    cmd = [
        "STAR",
        "--runMode",
        inp.run_mode,
        "--genomeDir",
        inp.genome_dir,
        "--readFilesIn",
        inp.fastq_r1,
    ]
    if inp.fastq_r2:
        cmd.append(inp.fastq_r2)

    cmd += [
        "--outFileNamePrefix",
        output_prefix,
        "--runThreadN",
        str(inp.threads),
        "--outSAMtype",
        *inp.out_sam_type.split(),
    ]

    if quant_mode != "None":
        cmd += ["--quantMode", quant_mode]

    if inp.fastq_r1.endswith(".gz"):
        cmd += ["--readFilesCommand", "zcat"]

    cmd += inp.extra_args
    return cmd


def _read_log_final(log_path: str) -> dict:  # type: ignore[type-arg]
    try:
        with open(log_path) as fh:
            return parse_star_log_final(fh.read())
    except OSError:
        return {}


@tool_call
def run_star_align(inp: STARAlignInput) -> STARAlignOutput:
    """Run STAR alignment in genome, transcriptome, or both modes.

    ``alignment_mode="both"`` executes two STAR subprocess calls: one for
    genome-sorted output (GeneCounts) and one for transcriptome output
    (TranscriptomeSAM) at a ``_tx_`` sub-prefix.
    """
    output_dir = str(Path(inp.output_prefix).parent)
    os.makedirs(output_dir, exist_ok=True)

    version = detect_version(["STAR", "--version"], "STAR")

    if inp.alignment_mode == "genome":
        cmd = _build_star_cmd(inp, inp.output_prefix, inp.quantification_mode)
        run_subprocess(cmd, tool_name="STAR")

        bam_path = f"{inp.output_prefix}Aligned.sortedByCoord.out.bam"
        log_final_path = f"{inp.output_prefix}Log.final.out"
        sj_path = f"{inp.output_prefix}SJ.out.tab"
        gene_counts_path: str | None = (
            f"{inp.output_prefix}ReadsPerGene.out.tab"
            if inp.quantification_mode == "GeneCounts"
            else None
        )
        tx_bam: str | None = None

    elif inp.alignment_mode == "transcriptome":
        cmd = _build_star_cmd(inp, inp.output_prefix, "TranscriptomeSAM")
        run_subprocess(cmd, tool_name="STAR")

        bam_path = f"{inp.output_prefix}Aligned.sortedByCoord.out.bam"
        log_final_path = f"{inp.output_prefix}Log.final.out"
        sj_path = f"{inp.output_prefix}SJ.out.tab"
        gene_counts_path = None
        tx_bam = f"{inp.output_prefix}Aligned.toTranscriptome.out.bam"

    else:  # "both" — two subprocess calls
        # First pass: genome + gene counts
        cmd = _build_star_cmd(inp, inp.output_prefix, "GeneCounts")
        run_subprocess(cmd, tool_name="STAR")

        # Second pass: transcriptome BAM at a separate prefix
        tx_prefix = f"{inp.output_prefix}_tx_"
        cmd2 = _build_star_cmd(inp, tx_prefix, "TranscriptomeSAM")
        run_subprocess(cmd2, tool_name="STAR")

        bam_path = f"{inp.output_prefix}Aligned.sortedByCoord.out.bam"
        log_final_path = f"{inp.output_prefix}Log.final.out"
        sj_path = f"{inp.output_prefix}SJ.out.tab"
        gene_counts_path = f"{inp.output_prefix}ReadsPerGene.out.tab"
        tx_bam = f"{tx_prefix}Aligned.toTranscriptome.out.bam"

    alignment_stats = _read_log_final(log_final_path)

    return STARAlignOutput(
        bam_path=bam_path,
        bam_index_path=f"{bam_path}.bai",
        log_final_path=log_final_path,
        splice_junctions_path=sj_path,
        gene_counts_path=gene_counts_path,
        transcriptome_bam_path=tx_bam,
        alignment_stats=alignment_stats,
        tool_version=version,
    )
