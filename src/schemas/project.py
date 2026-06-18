from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.db.enums import SampleType
from src.schemas.common import OrmBase


class ProjectCreate(OrmBase):
    name: str = Field(..., max_length=128)
    description: str | None = None
    owner: str = Field(..., max_length=64)


class ProjectRead(ProjectCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime


class SampleCreate(OrmBase):
    name: str = Field(..., max_length=128)
    sample_type: SampleType
    condition: str | None = Field(None, max_length=64)
    replicate: int | None = None
    fastq_r1_path: str
    fastq_r2_path: str | None = None
    is_paired_end: bool
    sample_metadata: dict | None = Field(None, alias="metadata")

    model_config = OrmBase.model_config.copy()
    model_config["populate_by_name"] = True


class SampleRead(SampleCreate):
    id: UUID
    project_id: UUID
    created_at: datetime
