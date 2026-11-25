"""API key principal + admin flag (per-principal data ownership).

Adds ``api_keys.principal`` (backfilled ``'default'``) and ``api_keys.is_admin`` (backfilled
false). Revision 0001 builds tables from the current models (``create_all``), so on a fresh
database these columns already exist; this revision only adds what is missing.

After upgrading a database with existing data, align ownership by hand, e.g.::

    UPDATE api_keys SET principal = 'team_a' WHERE name IN (...);
    UPDATE projects SET owner = 'team_a' WHERE ...;

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

_INDEX = "ix_api_keys_principal"


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("api_keys")}


def _indexes() -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("api_keys")}


def upgrade() -> None:
    cols = _columns()
    with op.batch_alter_table("api_keys") as batch:
        if "principal" not in cols:
            batch.add_column(
                sa.Column("principal", sa.String(64), nullable=False, server_default="default")
            )
        if "is_admin" not in cols:
            batch.add_column(
                sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
            )
    if _INDEX not in _indexes():
        op.create_index(_INDEX, "api_keys", ["principal"])


def downgrade() -> None:
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name="api_keys")
    cols = _columns()
    with op.batch_alter_table("api_keys") as batch:
        if "is_admin" in cols:
            batch.drop_column("is_admin")
        if "principal" in cols:
            batch.drop_column("principal")
