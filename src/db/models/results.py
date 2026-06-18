import uuid

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUIDPrimaryKeyMixin
from src.db.enums import PassFail, SplicingEventType


class QCMetric(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "qc_metrics"

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("samples.id"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_value_str: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pass_fail: Mapped[PassFail | None] = mapped_column(
        SAEnum(PassFail, native_enum=False), nullable=True
    )

    stage: Mapped["PipelineStage"] = relationship("PipelineStage")  # type: ignore[name-defined]  # noqa: F821
    sample: Mapped["Sample"] = relationship("Sample")  # type: ignore[name-defined]  # noqa: F821


class DEGResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "deg_results"
    __table_args__ = (Index("ix_deg_results_run_contrast_padj", "run_id", "contrast", "padj"),)

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False
    )
    contrast: Mapped[str] = mapped_column(String(128), nullable=False)
    gene_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gene_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basemean: Mapped[float | None] = mapped_column(Float, nullable=True)
    log2_fold_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    lfcse: Mapped[float | None] = mapped_column(Float, nullable=True)
    stat: Mapped[float | None] = mapped_column(Float, nullable=True)
    pvalue: Mapped[float | None] = mapped_column(Float, nullable=True)
    padj: Mapped[float | None] = mapped_column(Float, nullable=True)

    stage: Mapped["PipelineStage"] = relationship("PipelineStage")  # type: ignore[name-defined]  # noqa: F821
    run: Mapped["AnalysisRun"] = relationship("AnalysisRun")  # type: ignore[name-defined]  # noqa: F821


class GSEAResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "gsea_results"

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False
    )
    contrast: Mapped[str] = mapped_column(String(128), nullable=False)
    pathway_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pathway_name: Mapped[str] = mapped_column(Text, nullable=False)
    nes: Mapped[float | None] = mapped_column(Float, nullable=True)
    pvalue: Mapped[float | None] = mapped_column(Float, nullable=True)
    padj: Mapped[float | None] = mapped_column(Float, nullable=True)
    leading_edge_genes: Mapped[str | None] = mapped_column(Text, nullable=True)

    stage: Mapped["PipelineStage"] = relationship("PipelineStage")  # type: ignore[name-defined]  # noqa: F821
    run: Mapped["AnalysisRun"] = relationship("AnalysisRun")  # type: ignore[name-defined]  # noqa: F821


class SplicingResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "splicing_results"

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False
    )
    contrast: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[SplicingEventType] = mapped_column(
        SAEnum(SplicingEventType, native_enum=False), nullable=False
    )
    gene_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gene_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inclusion_level_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    pvalue: Mapped[float | None] = mapped_column(Float, nullable=True)
    fdr: Mapped[float | None] = mapped_column(Float, nullable=True)

    stage: Mapped["PipelineStage"] = relationship("PipelineStage")  # type: ignore[name-defined]  # noqa: F821
    run: Mapped["AnalysisRun"] = relationship("AnalysisRun")  # type: ignore[name-defined]  # noqa: F821


class VariantCall(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "variant_calls"

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("samples.id"), nullable=False
    )
    chrom: Mapped[str] = mapped_column(String(32), nullable=False)
    pos: Mapped[int] = mapped_column(Integer, nullable=False)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    alt: Mapped[str] = mapped_column(Text, nullable=False)
    qual: Mapped[float | None] = mapped_column(Float, nullable=True)
    filter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    info: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    stage: Mapped["PipelineStage"] = relationship("PipelineStage")  # type: ignore[name-defined]  # noqa: F821
    sample: Mapped["Sample"] = relationship("Sample")  # type: ignore[name-defined]  # noqa: F821


class ScRNAClusterResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scrna_cluster_results"

    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("samples.id"), nullable=False
    )
    n_clusters: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    n_cells: Mapped[int] = mapped_column(Integer, nullable=False)
    top_marker_genes: Mapped[str | None] = mapped_column(Text, nullable=True)

    stage: Mapped["PipelineStage"] = relationship("PipelineStage")  # type: ignore[name-defined]  # noqa: F821
    run: Mapped["AnalysisRun"] = relationship("AnalysisRun")  # type: ignore[name-defined]  # noqa: F821
    sample: Mapped["Sample"] = relationship("Sample")  # type: ignore[name-defined]  # noqa: F821
