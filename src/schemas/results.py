from uuid import UUID

from pydantic import Field, field_validator

from src.db.enums import PassFail, SplicingEventType
from src.schemas.common import OrmBase


class QCMetricRead(OrmBase):
    id: UUID
    stage_id: UUID
    sample_id: UUID
    metric_name: str
    metric_value: float | None
    metric_value_str: str | None
    pass_fail: PassFail | None


class DEGResultRead(OrmBase):
    id: UUID
    stage_id: UUID
    run_id: UUID
    contrast: str
    gene_id: str
    gene_name: str | None
    basemean: float | None
    log2_fold_change: float | None
    lfcse: float | None
    stat: float | None
    pvalue: float | None
    padj: float | None


class GSEAResultRead(OrmBase):
    id: UUID
    stage_id: UUID
    run_id: UUID
    contrast: str
    pathway_id: str
    pathway_name: str
    nes: float | None
    pvalue: float | None
    padj: float | None
    leading_edge_genes: list[str] = Field(default_factory=list)

    @field_validator("leading_edge_genes", mode="before")
    @classmethod
    def _parse_leading_edge(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [g.strip() for g in v.split(",") if g.strip()]
        return list(v)  # type: ignore[arg-type]


class SplicingResultRead(OrmBase):
    id: UUID
    stage_id: UUID
    run_id: UUID
    contrast: str
    event_type: SplicingEventType
    gene_id: str
    gene_name: str | None
    inclusion_level_diff: float | None
    pvalue: float | None
    fdr: float | None


class VariantCallRead(OrmBase):
    id: UUID
    stage_id: UUID
    sample_id: UUID
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float | None
    filter: str | None
    info: dict | None


class ScRNAClusterResultRead(OrmBase):
    id: UUID
    stage_id: UUID
    run_id: UUID
    sample_id: UUID
    n_clusters: int
    cluster_id: int
    n_cells: int
    top_marker_genes: list[str] = Field(default_factory=list)

    @field_validator("top_marker_genes", mode="before")
    @classmethod
    def _parse_marker_genes(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [g.strip() for g in v.split(",") if g.strip()]
        return list(v)  # type: ignore[arg-type]
