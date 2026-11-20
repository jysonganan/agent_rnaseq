import re
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from src.db.enums import (
    Aligner,
    AlignmentMode,
    ArtifactType,
    Executor,
    PipelineType,
    RunStatus,
    StageName,
    StageStatus,
)
from src.schemas.common import OrmBase


class ExecutionConfig(OrmBase):
    executor: Executor = Executor.local
    cpus: int = Field(default=4, ge=1, le=256)
    memory_gb: int = Field(default=16, ge=1, le=512)


_CONTRAST_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def default_contrast_name(numerator: str, denominator: str) -> str:
    """Deterministic, filename-safe contrast name: ``<numerator>_vs_<denominator>``."""
    raw = f"{numerator}_vs_{denominator}"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_.-") or "contrast"
    return safe[:128]


class DEContrast(OrmBase):
    """One comparison: ``numerator`` (test) vs ``denominator`` (reference).

    log2 fold change = numerator / denominator. Used by DESeq2 and rMATS.
    """

    name: str | None = Field(default=None, max_length=128)
    numerator: str = Field(..., min_length=1, max_length=64)
    denominator: str = Field(..., min_length=1, max_length=64)

    @field_validator("numerator", "denominator", "name", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.numerator == self.denominator:
            raise ValueError(f"contrast compares '{self.numerator}' with itself")
        if not self.name:
            self.name = default_contrast_name(self.numerator, self.denominator)
        if not _CONTRAST_NAME_RE.match(self.name):
            raise ValueError(f"contrast name '{self.name}' must match {_CONTRAST_NAME_RE.pattern}")
        return self


class AnalysisRunCreate(OrmBase):
    project_id: UUID
    genome_id: UUID
    name: str = Field(..., max_length=128)
    pipeline_type: PipelineType
    sample_ids: list[UUID]
    alignment_mode: AlignmentMode = AlignmentMode.genome
    aligner: Aligner = Aligner.star
    stages: list[StageName]
    de_contrasts: list[DEContrast] = []
    read_length: int | None = Field(default=None, ge=1, le=1000)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    dry_run: bool = False

    @field_validator("stages")
    @classmethod
    def stages_not_empty(cls, v: list[StageName]) -> list[StageName]:
        if not v:
            raise ValueError("stages must not be empty")
        return v

    @field_validator("sample_ids")
    @classmethod
    def sample_ids_not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("sample_ids must not be empty")
        return v


class AnalysisRunRead(OrmBase):
    id: UUID
    project_id: UUID
    genome_id: UUID
    name: str
    status: RunStatus
    pipeline_type: PipelineType
    alignment_mode: AlignmentMode
    aligner: Aligner
    run_config: dict
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class PipelineStageRead(OrmBase):
    id: UUID
    run_id: UUID
    sample_id: UUID | None
    stage_name: StageName
    status: StageStatus
    tool_name: str
    tool_version: str | None
    executor: Executor | None
    exit_code: int | None
    log_path: str | None
    started_at: datetime | None
    completed_at: datetime | None


class ArtifactRead(OrmBase):
    id: UUID
    stage_id: UUID
    run_id: UUID
    artifact_type: ArtifactType
    path: str
    file_size_bytes: int | None
    checksum_md5: str | None
    created_at: datetime
