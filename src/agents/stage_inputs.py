"""Deterministic construction of specialist ``StageInput`` dicts.

The LangGraph state only carries ``run_config`` and prior ``stage_outputs``. Each
specialist, however, needs concrete file paths (FASTQs, genome indices, BAMs, counts
matrices). This module resolves them from the DB (``AnalysisRun`` → samples, genome)
and from upstream stage outputs. No LLM is involved anywhere in this module.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.db.enums import Aligner, AlignmentMode, PipelineType

_REPO_ROOT = Path(__file__).resolve().parents[2]
DESEQ2_R_SCRIPT = str(_REPO_ROOT / "src" / "r" / "deseq2_analysis.R")
REACTOME_R_SCRIPT = str(_REPO_ROOT / "src" / "r" / "reactome_gsea.R")
SCANPY_SCRIPT = str(_REPO_ROOT / "src" / "scripts" / "scanpy_pipeline.py")
REPORT_TEMPLATE = str(_REPO_ROOT / "src" / "tools" / "report" / "template.html")

# Stages that run once per sample / once per user contrast; all others once per run.
PER_SAMPLE_STAGES: frozenset[str] = frozenset(
    {"qc", "alignment", "quantification", "variant_calling", "scrna_seq"}
)
PER_CONTRAST_STAGES: frozenset[str] = frozenset({"splicing"})

_ORGANISMS: dict[str, str] = {
    "human": "human",
    "homo sapiens": "human",
    "homo_sapiens": "human",
    "mouse": "mouse",
    "mus musculus": "mouse",
    "mus_musculus": "mouse",
}


class StageInputError(Exception):
    """Raised when a stage cannot be configured from the run's DB records/outputs."""


@dataclass(frozen=True)
class SampleInfo:
    id: str
    name: str
    condition: str | None
    fastq_r1: str
    fastq_r2: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenomeInfo:
    build: str
    species: str
    fasta_path: str
    gtf_path: str
    star_index_path: str | None
    salmon_index_path: str | None
    rsem_index_path: str | None


@dataclass(frozen=True)
class PipelineContext:
    run_id: str
    run_name: str
    pipeline_type: PipelineType
    aligner: Aligner
    alignment_mode: AlignmentMode
    run_config: dict[str, Any]
    genome: GenomeInfo
    samples: list[SampleInfo]
    output_root: str
    # executor=aws_batch: heavy (Nextflow) stages publish under this s3:// root
    remote_output_root: str | None = None
    # makes a (possibly remote) file readable by worker-side stages; identity when local
    localize: Callable[[str], str] = field(default=lambda p: p, compare=False)

    @property
    def threads(self) -> int:
        execution = self.run_config.get("execution") or {}
        return int(execution.get("cpus", 8))

    @property
    def executor(self) -> str:
        execution = self.run_config.get("execution") or {}
        return str(execution.get("executor") or self.run_config.get("executor") or "local")

    def stage_dir(self, stage: str, sample_id: str | None = None) -> str:
        parts = [self.output_root, self.run_id, stage]
        if sample_id:
            parts.append(sample_id)
        return os.path.join(*parts)

    def heavy_stage_dir(self, stage: str, sample_id: str) -> str:
        """Output dir of a stage that may run on Nextflow/AWS Batch (S3 when remote)."""
        if self.remote_output_root:
            return posixpath.join(self.remote_output_root, self.run_id, stage, sample_id)
        return self.stage_dir(stage, sample_id)


def load_pipeline_context(db: Session, run_id: str, output_root: str) -> PipelineContext:
    """Load everything a run needs from the DB into an immutable context."""
    from src.db.models.project import Sample
    from src.db.models.run import AnalysisRun

    run = db.get(AnalysisRun, uuid.UUID(run_id))
    if run is None:
        raise StageInputError(f"Run {run_id} not found")

    samples = [assoc.sample for assoc in run.sample_associations]
    if not samples:
        # Fallback for runs whose RunSample rows were not written.
        ids = [uuid.UUID(s) for s in (run.run_config or {}).get("sample_ids", [])]
        samples = db.query(Sample).filter(Sample.id.in_(ids)).all() if ids else []
    if not samples:
        raise StageInputError(f"Run {run_id} has no samples attached")

    g = run.genome
    return PipelineContext(
        run_id=run_id,
        run_name=run.name,
        pipeline_type=run.pipeline_type,
        aligner=run.aligner,
        alignment_mode=run.alignment_mode,
        run_config=dict(run.run_config or {}),
        genome=GenomeInfo(
            build=g.build,
            species=g.species,
            fasta_path=g.fasta_path,
            gtf_path=g.gtf_path,
            star_index_path=g.star_index_path,
            salmon_index_path=g.salmon_index_path,
            rsem_index_path=g.rsem_index_path,
        ),
        samples=sorted(
            (
                SampleInfo(
                    id=str(s.id),
                    name=s.name,
                    condition=s.condition,
                    fastq_r1=s.fastq_r1_path,
                    fastq_r2=s.fastq_r2_path,
                    metadata=dict(s.sample_metadata or {}),
                )
                for s in samples
            ),
            key=lambda s: s.name,
        ),
        output_root=output_root,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _require(value: str | None, what: str) -> str:
    if not value:
        raise StageInputError(f"{what} is not configured")
    return value


def _per_sample_output(stage_outputs: dict, stage: str, sample_id: str) -> dict:
    """Return the tool output dict of ``stage`` for one sample (``{}`` if absent)."""
    entry = stage_outputs.get(stage) or {}
    sample_entry = (entry.get("samples") or {}).get(sample_id) or {}
    return sample_entry.get("output") or {}


def _aggregate_output(stage_outputs: dict, stage: str) -> dict:
    entry = stage_outputs.get(stage) or {}
    return entry.get("output") or {}


def _bam_for(stage_outputs: dict, sample_id: str) -> tuple[str, str]:
    out = _per_sample_output(stage_outputs, "alignment", sample_id)
    bam = out.get("sorted_bam_path") or out.get("bam_path")
    bai = out.get("sorted_bai_path") or out.get("bam_index_path")
    if not bam or not bai:
        raise StageInputError(f"No aligned BAM available for sample {sample_id}")
    return bam, bai


def quantification_method(ctx: PipelineContext) -> str:
    return {
        Aligner.star: "star_htseq",
        Aligner.salmon: "salmon",
        Aligner.rsem: "rsem",
    }[Aligner(ctx.aligner)]


def resolve_contrasts(ctx: PipelineContext) -> list[dict[str, str]]:
    """The user's contrasts from the run config (validated; any number of conditions).

    Never derived: which conditions to compare, and in which direction, is the user's
    decision (asked for by the API / chat before the run is created).
    """
    from src.schemas.run import DEContrast

    raw = ctx.run_config.get("de_contrasts") or []
    if not raw:
        raise StageInputError("No de_contrasts in the run config; the user must specify them")
    contrasts = [DEContrast.model_validate(c) for c in raw]
    return [
        {"name": c.name or "", "numerator": c.numerator, "denominator": c.denominator}
        for c in contrasts
    ]


def _organism(ctx: PipelineContext) -> str:
    org = _ORGANISMS.get(ctx.genome.species.strip().lower())
    if org is None:
        raise StageInputError(
            f"Reactome GSEA supports human or mouse only; genome species is {ctx.genome.species!r}"
        )
    return org


def _read_length(ctx: PipelineContext) -> int:
    from src.agents.run_requirements import SampleFacts, resolve_read_length

    facts = [
        SampleFacts(s.id, s.name, s.condition, s.metadata.get("read_length")) for s in ctx.samples
    ]
    value = resolve_read_length(ctx.run_config.get("read_length"), facts)
    if value is None:
        raise StageInputError(
            "Splicing needs a read length: set run_config.read_length or "
            "samples' metadata.read_length"
        )
    return int(value)


# ── Per-stage builders ─────────────────────────────────────────────────────────


def _qc(ctx: PipelineContext, s: SampleInfo, outs: dict) -> dict:
    bam_path = bai_path = None
    if "alignment" in outs:
        bam_path, bai_path = _bam_for(outs, s.id)
    return {
        "run_id": ctx.run_id,
        "sample_id": s.id,
        "fastq_paths": [p for p in (s.fastq_r1, s.fastq_r2) if p],
        "output_dir": ctx.heavy_stage_dir("qc", s.id),
        "bam_path": bam_path,
        "bam_index_path": bai_path,
        "bed_annotation_path": ctx.run_config.get("bed_annotation_path"),
    }


def _alignment(ctx: PipelineContext, s: SampleInfo, outs: dict) -> dict:
    out_dir = ctx.heavy_stage_dir("alignment", s.id)
    return {
        "run_id": ctx.run_id,
        "sample_id": s.id,
        "fastq_r1": s.fastq_r1,
        "fastq_r2": s.fastq_r2,
        "genome_dir": _require(ctx.genome.star_index_path, "Genome STAR index"),
        "output_prefix": posixpath.join(out_dir, s.name + "_"),
        "threads": ctx.threads,
        "alignment_mode": _star_alignment_mode(ctx),
        "read_group": _read_group(s),
    }


def _read_group(s: SampleInfo) -> str:
    """Filename/RG-safe sample label: the sample name, sanitised (falls back to the id)."""
    label = re.sub(r"[^A-Za-z0-9_.:-]+", "_", s.name).strip("_")
    return label[:128] or s.id


def _star_alignment_mode(ctx: PipelineContext) -> str:
    mode = AlignmentMode(ctx.alignment_mode)
    # RSEM quantifies from a transcriptome BAM, so STAR must also emit one.
    if Aligner(ctx.aligner) == Aligner.rsem and mode == AlignmentMode.genome:
        return AlignmentMode.both.value
    return mode.value


def _quantification(ctx: PipelineContext, s: SampleInfo, outs: dict) -> dict:
    method = quantification_method(ctx)
    inp: dict[str, Any] = {
        "run_id": ctx.run_id,
        "sample_id": s.id,
        "quantification_method": method,
        "output_dir": ctx.heavy_stage_dir("quantification", s.id),
        "bam_path": None,
        "gtf_path": None,
        "fastq_r1": None,
        "fastq_r2": None,
        "index_path": None,
        "rsem_reference": None,
    }
    if method == "star_htseq":
        inp["bam_path"], _ = _bam_for(outs, s.id)
        inp["gtf_path"] = ctx.genome.gtf_path
    elif method == "salmon":
        inp["fastq_r1"], inp["fastq_r2"] = s.fastq_r1, s.fastq_r2
        inp["index_path"] = _require(ctx.genome.salmon_index_path, "Genome Salmon index")
    else:
        align = _per_sample_output(outs, "alignment", s.id)
        bam = align.get("transcriptome_bam_path")
        if not bam:
            raise StageInputError(
                f"RSEM needs a transcriptome BAM for sample {s.id}; "
                "run alignment with alignment_mode 'transcriptome' or 'both'"
            )
        inp["bam_path"] = bam
        inp["rsem_reference"] = _require(ctx.genome.rsem_index_path, "Genome RSEM index")
    return inp


def _variant(ctx: PipelineContext, s: SampleInfo, outs: dict) -> dict:
    bam, bai = _bam_for(outs, s.id)
    return {
        "run_id": ctx.run_id,
        "sample_id": s.id,
        "bam_path": bam,
        "bam_index_path": bai,
        "reference_fasta": ctx.genome.fasta_path,
        "output_dir": ctx.heavy_stage_dir("variant_calling", s.id),
        "dbsnp_path": ctx.run_config.get("dbsnp_path"),
    }


def _scrna(ctx: PipelineContext, s: SampleInfo, outs: dict) -> dict:
    fastq_dirs = s.metadata.get("fastq_dirs") or [os.path.dirname(s.fastq_r1)]
    return {
        "run_id": ctx.run_id,
        "sample_id": s.id,
        "fastq_dirs": list(fastq_dirs),
        "sample_name": s.metadata.get("cellranger_sample_name", s.name),
        "transcriptome_path": _require(
            ctx.run_config.get("cellranger_transcriptome_path")
            or s.metadata.get("cellranger_transcriptome_path"),
            "CellRanger transcriptome (run_config.cellranger_transcriptome_path)",
        ),
        "output_dir": ctx.stage_dir("scrna_seq", s.id),
        "script_path": SCANPY_SCRIPT,
    }


def _splicing(ctx: PipelineContext, outs: dict) -> list[dict]:
    """One rMATS run per user contrast: group 1 = numerator, group 2 = denominator."""
    read_length = _read_length(ctx)
    inputs = []
    for contrast in resolve_contrasts(ctx):
        b1 = [
            ctx.localize(_bam_for(outs, s.id)[0])
            for s in ctx.samples
            if s.condition == contrast["numerator"]
        ]
        b2 = [
            ctx.localize(_bam_for(outs, s.id)[0])
            for s in ctx.samples
            if s.condition == contrast["denominator"]
        ]
        if not b1 or not b2:
            raise StageInputError(f"Contrast {contrast['name']} has an empty sample group")
        inputs.append(
            {
                "run_id": ctx.run_id,
                "bam_list_b1": b1,
                "bam_list_b2": b2,
                "gtf_path": ctx.genome.gtf_path,
                "output_dir": os.path.join(ctx.stage_dir("splicing"), contrast["name"]),
                "read_length": read_length,
                "contrast": contrast["name"],
            }
        )
    return inputs


def _de(ctx: PipelineContext, outs: dict) -> dict:
    from src.tools.de.count_matrix import (
        CountMatrixInput,
        SampleMetadataInput,
        build_count_matrix,
        write_sample_metadata,
    )

    method = quantification_method(ctx)
    key = {"star_htseq": "counts_path", "salmon": "quant_sf_path", "rsem": "genes_results_path"}[
        method
    ]
    count_paths: dict[str, str] = {}
    for s in ctx.samples:
        path = _per_sample_output(outs, "quantification", s.id).get(key)
        if not path:
            raise StageInputError(f"No quantification output for sample {s.id}")
        count_paths[s.id] = ctx.localize(path)

    out_dir = ctx.stage_dir("differential_expression")
    matrix = build_count_matrix(
        CountMatrixInput(
            sample_count_paths=count_paths,
            method=method,  # type: ignore[arg-type]
            output_path=os.path.join(out_dir, "counts_matrix.csv"),
        )
    )
    metadata_path = write_sample_metadata(
        SampleMetadataInput(
            sample_conditions={s.id: s.condition or "" for s in ctx.samples},
            output_path=os.path.join(out_dir, "sample_metadata.csv"),
        )
    )
    return {
        "run_id": ctx.run_id,
        "counts_matrix_path": matrix.counts_matrix_path,
        "sample_metadata_path": metadata_path,
        "contrasts": resolve_contrasts(ctx),
        "output_dir": out_dir,
        "alpha": float(ctx.run_config.get("alpha", 0.05)),
        "lfc_threshold": float(ctx.run_config.get("lfc_threshold", 0.0)),
        "r_script_path": DESEQ2_R_SCRIPT,
    }


def _gsea(ctx: PipelineContext, outs: dict) -> dict:
    results_paths = _aggregate_output(outs, "differential_expression").get("results_paths") or {}
    if not results_paths:
        raise StageInputError("GSEA needs differential expression results")
    return {
        "run_id": ctx.run_id,
        "de_results_paths": dict(results_paths),
        "output_dir": ctx.stage_dir("gsea"),
        "organism": _organism(ctx),
        "r_script_path": REACTOME_R_SCRIPT,
    }


def _write_qc_metrics(ctx: PipelineContext, outs: dict, path: str) -> str | None:
    """QC metrics JSON for the dashboard, copied from validated QC/alignment outputs."""
    if "qc" not in outs and "alignment" not in outs:
        return None
    samples = []
    for s in ctx.samples:
        fastqc = _per_sample_output(outs, "qc", s.id).get("summary") or {}
        stats = _per_sample_output(outs, "alignment", s.id).get("alignment_stats") or {}
        statuses = [str(v).upper() for v in fastqc.values()]
        row: dict[str, Any] = {"sample": s.name, "condition": s.condition or ""}
        if "total_reads" in stats:
            row["total_reads"] = stats["total_reads"]
        if "uniquely_mapped_pct" in stats:
            row["mapping_rate"] = stats["uniquely_mapped_pct"]
        if statuses:
            row.update(
                fastqc_pass=statuses.count("PASS"),
                fastqc_warn=statuses.count("WARN"),
                fastqc_fail=statuses.count("FAIL"),
            )
        samples.append(row)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"samples": samples}, fh, indent=2)
    return path


def _visualization(ctx: PipelineContext, outs: dict) -> dict:
    bam_paths: list[str] = []
    if "alignment" in outs:
        for s in ctx.samples:
            bam, bai = _bam_for(outs, s.id)
            ctx.localize(bai)  # bamCoverage needs the index next to the BAM
            bam_paths.append(ctx.localize(bam))
    out_dir = ctx.stage_dir("visualization")
    fai = ctx.genome.fasta_path + ".fai"
    return {
        "run_id": ctx.run_id,
        "de_results_dir": ctx.stage_dir("differential_expression")
        if "differential_expression" in outs
        else None,
        "gsea_results_dir": ctx.stage_dir("gsea") if "gsea" in outs else None,
        "qc_metrics_path": _write_qc_metrics(
            ctx, outs, os.path.join(out_dir, "inputs", "qc_metrics.json")
        ),
        "bam_paths": bam_paths,
        "genome_build": ctx.genome.build,
        "output_dir": out_dir,
        "track_name_prefix": ctx.run_name,
        "chrom_sizes_path": fai if os.path.isfile(fai) else None,
    }


def _report(ctx: PipelineContext, outs: dict) -> dict:
    def _summary(stage: str) -> dict | None:
        entry = outs.get(stage)
        if not entry:
            return None
        for key in ("samples", "contrasts"):
            if key in entry:
                return {k: o.get("output") for k, o in entry[key].items()}
        return entry.get("output")

    artifact_paths: dict[str, str] = {}
    de = _aggregate_output(outs, "differential_expression")
    for name, path in (de.get("results_paths") or {}).items():
        artifact_paths[f"de_{name}"] = path
    for name, entry in (_aggregate_output(outs, "gsea").get("per_contrast") or {}).items():
        artifact_paths[f"gsea_{name}"] = entry.get("results_path", "")
    viz = _aggregate_output(outs, "visualization")
    if viz.get("manifest_path"):
        artifact_paths["streamlit_manifest"] = viz["manifest_path"]
    if viz.get("track_hub_path"):
        artifact_paths["ucsc_track_hub"] = viz["track_hub_path"]

    return {
        "run_id": ctx.run_id,
        "run_name": ctx.run_name,
        "qc_summary": _summary("qc"),
        "de_summary": (de.get("contrast_summaries") or None),
        "gsea_summary": _aggregate_output(outs, "gsea").get("per_contrast") or None,
        "artifact_paths": artifact_paths,
        "output_dir": ctx.stage_dir("report"),
        "template_path": REPORT_TEMPLATE,
    }


_PER_SAMPLE_BUILDERS = {
    "qc": _qc,
    "alignment": _alignment,
    "quantification": _quantification,
    "variant_calling": _variant,
    "scrna_seq": _scrna,
}

_AGGREGATE_BUILDERS = {
    "differential_expression": _de,
    "gsea": _gsea,
    "visualization": _visualization,
    "report": _report,
}


def build_stage_inputs(
    stage: str, ctx: PipelineContext, stage_outputs: dict[str, dict]
) -> list[dict[str, Any]]:
    """Return the list of specialist inputs for ``stage`` (one per sample, or one total)."""
    if stage in _PER_SAMPLE_BUILDERS:
        builder = _PER_SAMPLE_BUILDERS[stage]
        return [builder(ctx, s, stage_outputs) for s in ctx.samples]
    if stage in PER_CONTRAST_STAGES:
        return _splicing(ctx, stage_outputs)
    if stage in _AGGREGATE_BUILDERS:
        return [_AGGREGATE_BUILDERS[stage](ctx, stage_outputs)]
    raise StageInputError(f"Unknown stage {stage!r}")
