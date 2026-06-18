import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, _utcnow
from src.db.enums import SampleType


class Project(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="project")
    runs: Mapped[list["AnalysisRun"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "AnalysisRun", back_populates="project"
    )


class Sample(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "samples"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sample_type: Mapped[SampleType] = mapped_column(
        SAEnum(SampleType, native_enum=False), nullable=False
    )
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replicate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fastq_r1_path: Mapped[str] = mapped_column(Text, nullable=False)
    fastq_r2_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_paired_end: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sample_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    project: Mapped[Project] = relationship("Project", back_populates="samples")
    run_associations: Mapped[list["RunSample"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "RunSample", back_populates="sample"
    )


class RunSample(Base):
    """Many-to-many join between AnalysisRun and Sample."""

    __tablename__ = "run_samples"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), primary_key=True
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("samples.id"), primary_key=True
    )

    run: Mapped["AnalysisRun"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "AnalysisRun", back_populates="sample_associations"
    )
    sample: Mapped[Sample] = relationship("Sample", back_populates="run_associations")
