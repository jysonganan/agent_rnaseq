"""Initial schema — all tables.

Revision ID: 0001
Revises:
Create Date: 2026-06-18

"""

from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Import after alembic env has set up sys.path
    import src.db.models  # noqa: F401 — side-effect: registers all models
    from src.db.base import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    import src.db.models  # noqa: F401
    from src.db.base import Base

    Base.metadata.drop_all(bind=op.get_bind())
