from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.schemas.common import OrmBase


class ReferenceGenomeCreate(OrmBase):
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


class ReferenceGenomeRead(ReferenceGenomeCreate):
    id: UUID
    created_at: datetime
    has_star_index: bool = False
    has_salmon_index: bool = False
    has_rsem_index: bool = False

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        instance = super().model_validate(obj, **kwargs)
        instance.has_star_index = bool(obj.star_index_path)
        instance.has_salmon_index = bool(obj.salmon_index_path)
        instance.has_rsem_index = bool(obj.rsem_index_path)
        return instance
