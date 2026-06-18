from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class ReferenceGenome(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reference_genomes"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    species: Mapped[str] = mapped_column(String(64), nullable=False)
    build: Mapped[str] = mapped_column(String(32), nullable=False)
    annotation_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fasta_path: Mapped[str] = mapped_column(Text, nullable=False)
    gtf_path: Mapped[str] = mapped_column(Text, nullable=False)
    star_index_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    star_txome_index_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    salmon_index_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    rsem_index_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    runs: Mapped[list["AnalysisRun"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "AnalysisRun", back_populates="genome"
    )
