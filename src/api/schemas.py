"""Pydantic request/response schemas for the FastAPI service."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.db.enums import (
    Aligner,
    AlignmentMode,
    ArtifactType,
    Executor,
    PassFail,
    PipelineType,
    RunStatus,
    SampleType,
    SplicingEventType,
    StageName,
    StageStatus,
)

# ── Genomes ────────────────────────────────────────────────────────────────────


class GenomeOut(BaseModel):
    id: uuid.UUID
    name: str
    species: str
    build: str
    annotation_version: str | None
    fasta_path: str
    gtf_path: str
    star_index_path: str | None
    salmon_index_path: str | None
    rsem_index_path: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateGenomeIn(BaseModel):
    name: str = Field(..., max_length=64)
    species: str = Field(..., max_length=64)
    build: str = Field(..., max_length=32)
    annotation_version: str | None = Field(None, max_length=32)
    fasta_path: str
    gtf_path: str
    star_index_path: str | None = None
    star_txome_index_path: str | None = None
    salmon_index_path: str | None = None
    rsem_index_path: str | None = None


class GenomeListOut(BaseModel):
    items: list[GenomeOut]
    total: int
    limit: int
    offset: int


# ── Projects ──────────────────────────────────────────────────────────────────


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateProjectIn(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = None
    owner: str = Field(..., max_length=64)


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int
    limit: int
    offset: int


# ── Samples ───────────────────────────────────────────────────────────────────


class SampleOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    sample_type: SampleType
    condition: str | None
    replicate: int | None
    fastq_r1_path: str
    fastq_r2_path: str | None
    is_paired_end: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateSampleIn(BaseModel):
    name: str = Field(..., max_length=128)
    sample_type: SampleType
    condition: str | None = None
    replicate: int | None = None
    fastq_r1_path: str
    fastq_r2_path: str | None = None
    is_paired_end: bool = True


class SampleListOut(BaseModel):
    items: list[SampleOut]
    total: int


# ── Runs ──────────────────────────────────────────────────────────────────────


class ExecutionConfigIn(BaseModel):
    executor: Executor = Executor.local
    cpus: int = Field(default=4, ge=1, le=128)
    memory_gb: int = Field(default=16, ge=1, le=512)


class CreateRunIn(BaseModel):
    project_id: uuid.UUID
    genome_id: uuid.UUID
    name: str = Field(..., max_length=128)
    pipeline_type: PipelineType
    sample_ids: list[uuid.UUID] = Field(..., min_length=1)
    alignment_mode: AlignmentMode
    aligner: Aligner
    stages: list[StageName] = Field(..., min_length=1)
    de_contrasts: list[dict] = Field(default_factory=list)
    execution: ExecutionConfigIn = Field(default_factory=ExecutionConfigIn)


class StageOut(BaseModel):
    id: uuid.UUID
    stage_name: StageName
    status: StageStatus
    tool_name: str
    tool_version: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    genome_id: uuid.UUID
    name: str
    status: RunStatus
    pipeline_type: PipelineType
    alignment_mode: AlignmentMode
    aligner: Aligner
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class RunDetailOut(RunOut):
    stages: list[StageOut] = []


class RunCreatedOut(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    message: str


class RunListOut(BaseModel):
    items: list[RunOut]
    total: int


class CancelRunOut(BaseModel):
    run_id: uuid.UUID
    status: RunStatus


# ── Artifacts ─────────────────────────────────────────────────────────────────


class ArtifactOut(BaseModel):
    id: uuid.UUID
    artifact_type: ArtifactType
    path: str
    file_size_bytes: int | None
    checksum_md5: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListOut(BaseModel):
    items: list[ArtifactOut]
    total: int


class DownloadUrlOut(BaseModel):
    artifact_id: uuid.UUID
    url: str
    expires_in_seconds: int = 3600


# ── QC Metrics ────────────────────────────────────────────────────────────────


class QCMetricOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    metric_name: str
    metric_value: float | None
    metric_value_str: str | None
    pass_fail: PassFail | None

    model_config = {"from_attributes": True}


class QCMetricsOut(BaseModel):
    items: list[QCMetricOut]
    total: int


# ── DE Results ────────────────────────────────────────────────────────────────


class DEResultOut(BaseModel):
    id: uuid.UUID
    contrast: str
    gene_id: str
    gene_name: str | None
    basemean: float | None
    log2_fold_change: float | None
    pvalue: float | None
    padj: float | None

    model_config = {"from_attributes": True}


class DEResultsOut(BaseModel):
    items: list[DEResultOut]
    total: int
    limit: int
    offset: int


# ── GSEA Results ──────────────────────────────────────────────────────────────


class GSEAResultOut(BaseModel):
    id: uuid.UUID
    contrast: str
    pathway_id: str
    pathway_name: str
    nes: float | None
    pvalue: float | None
    padj: float | None
    leading_edge_genes: str | None

    model_config = {"from_attributes": True}


class GSEAResultsOut(BaseModel):
    items: list[GSEAResultOut]
    total: int
    limit: int
    offset: int


# ── Splicing Results ──────────────────────────────────────────────────────────


class SplicingResultOut(BaseModel):
    id: uuid.UUID
    contrast: str
    event_type: SplicingEventType
    gene_id: str
    gene_name: str | None
    inclusion_level_diff: float | None
    pvalue: float | None
    fdr: float | None

    model_config = {"from_attributes": True}


class SplicingResultsOut(BaseModel):
    items: list[SplicingResultOut]
    total: int
    limit: int
    offset: int


# ── Variant Calls ─────────────────────────────────────────────────────────────


class VariantOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float | None
    filter: str | None
    info: dict | None

    model_config = {"from_attributes": True}


class VariantListOut(BaseModel):
    items: list[VariantOut]
    total: int
    limit: int
    offset: int


# ── API Keys ──────────────────────────────────────────────────────────────────


class CreateAPIKeyIn(BaseModel):
    name: str = Field(..., max_length=128)
    expires_at: datetime | None = None


class APIKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    created_by: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    is_active: bool

    model_config = {"from_attributes": True}


class APIKeyCreateOut(APIKeyOut):
    raw_key: str


class APIKeyListOut(BaseModel):
    items: list[APIKeyOut]
    total: int
