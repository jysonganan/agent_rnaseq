import uuid

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
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


class AnalysisRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "analysis_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    genome_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reference_genomes.id"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, native_enum=False), nullable=False, default=RunStatus.pending
    )
    pipeline_type: Mapped[PipelineType] = mapped_column(
        SAEnum(PipelineType, native_enum=False), nullable=False
    )
    alignment_mode: Mapped[AlignmentMode] = mapped_column(
        SAEnum(AlignmentMode, native_enum=False), nullable=False
    )
    aligner: Mapped[Aligner] = mapped_column(SAEnum(Aligner, native_enum=False), nullable=False)
    run_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    agent_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Project", back_populates="runs"
    )
    genome: Mapped["ReferenceGenome"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ReferenceGenome", back_populates="runs"
    )
    api_key: Mapped["APIKey"] = relationship("APIKey")  # type: ignore[name-defined]  # noqa: F821
    sample_associations: Mapped[list["RunSample"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "RunSample", back_populates="run"
    )
    stages: Mapped[list["PipelineStage"]] = relationship("PipelineStage", back_populates="run")
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="run")


class PipelineStage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pipeline_stages"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False
    )
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("samples.id"), nullable=True
    )
    stage_name: Mapped[StageName] = mapped_column(
        SAEnum(StageName, native_enum=False), nullable=False
    )
    status: Mapped[StageStatus] = mapped_column(
        SAEnum(StageStatus, native_enum=False), nullable=False, default=StageStatus.pending
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executor: Mapped[Executor | None] = mapped_column(
        SAEnum(Executor, native_enum=False), nullable=True
    )
    batch_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[AnalysisRun] = relationship("AnalysisRun", back_populates="stages")
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="stage")


class Artifact(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "artifacts"

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(
        SAEnum(ArtifactType, native_enum=False), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)

    stage: Mapped[PipelineStage] = relationship("PipelineStage", back_populates="artifacts")
    run: Mapped[AnalysisRun] = relationship("AnalysisRun", back_populates="artifacts")
