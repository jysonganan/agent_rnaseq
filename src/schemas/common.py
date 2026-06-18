from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UUIDSchema(OrmBase):
    id: UUID


class TimestampSchema(OrmBase):
    created_at: datetime


class UUIDTimestampSchema(UUIDSchema, TimestampSchema):
    pass


class PaginatedResponse(BaseModel):
    total: int
