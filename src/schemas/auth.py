from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.schemas.common import OrmBase


class APIKeyCreate(OrmBase):
    name: str = Field(..., max_length=128)
    expires_at: datetime | None = None


class APIKeyRead(OrmBase):
    id: UUID
    name: str
    created_by: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class APIKeyCreatedResponse(APIKeyRead):
    """Returned once at key creation — includes the raw key (never stored)."""

    key: str = Field(..., description="Raw API key — shown once, never retrievable again")
