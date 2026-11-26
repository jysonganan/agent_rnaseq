"""ReferenceGenome.bed_annotation_path (BED12 gene model for RSeQC in ``alignment_qc``).

Revision 0001 builds tables from the current models (``create_all``), so on a fresh database
the column already exists; this revision only adds it when missing. The new ``alignment_qc``
stage and ``rseqc_report`` artifact type need no migration: enums are stored as non-native
VARCHAR and both values fit the existing column widths.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("reference_genomes")}


def upgrade() -> None:
    if "bed_annotation_path" not in _columns():
        with op.batch_alter_table("reference_genomes") as batch:
            batch.add_column(sa.Column("bed_annotation_path", sa.Text(), nullable=True))


def downgrade() -> None:
    if "bed_annotation_path" in _columns():
        with op.batch_alter_table("reference_genomes") as batch:
            batch.drop_column("bed_annotation_path")
