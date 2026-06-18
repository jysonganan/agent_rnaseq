from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class APIKey(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        now = datetime.now(UTC)
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at >= now
