"""convert_gtf_to_bed12 / ensure_gene_model_bed (tool_contracts.md ``convert_gtf_to_bed12``)."""

from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest

from src.tools.base import ToolValidationError
from src.tools.qc.gtf_to_bed import convert_gtf_to_bed12, ensure_gene_model_bed


def _gtf_line(chrom, feature, start, end, strand, tid):  # type: ignore[no-untyped-def]
    attrs = f'gene_id "G_{tid}"; transcript_id "{tid}";'
    return f"{chrom}\tsrc\t{feature}\t{start}\t{end}\t.\t{strand}\t.\t{attrs}\n"


# Coding transcript on + with exons listed out of order; non-coding on -; a transcript
# split across chromosomes (skipped); a gene line without transcript_id (ignored).
GTF = "".join(
    [
        "#!genome-build test\n",
        'chr1\tsrc\tgene\t100\t500\t.\t+\t.\tgene_id "G_T1";\n',
        _gtf_line("chr1", "transcript", 100, 500, "+", "T1"),
        _gtf_line("chr1", "exon", 401, 500, "+", "T1"),
        _gtf_line("chr1", "exon", 100, 200, "+", "T1"),
        _gtf_line("chr1", "CDS", 150, 200, "+", "T1"),
        _gtf_line("chr1", "CDS", 401, 450, "+", "T1"),
        _gtf_line("chr1", "stop_codon", 451, 453, "+", "T1"),
        _gtf_line("chr1", "exon", 1000, 1100, "-", "NC1"),
        _gtf_line("chr1", "exon", 1201, 1300, "-", "NC1"),
        _gtf_line("chr1", "exon", 50, 60, "+", "MIX"),
        _gtf_line("chr2", "exon", 50, 60, "+", "MIX"),
        _gtf_line("chr10", "exon", 5, 10, "+", "T2"),
    ]
)


def _bed(tmp_path: Path, text: str = GTF, gz: bool = False) -> list[list[str]]:
    gtf = tmp_path / ("g.gtf.gz" if gz else "g.gtf")
    if gz:
        gtf.write_bytes(gzip.compress(text.encode()))
    else:
        gtf.write_text(text)
    out = tmp_path / "out" / "genes.bed12"
    n = convert_gtf_to_bed12(str(gtf), str(out))
    rows = [line.split("\t") for line in out.read_text().splitlines()]
    assert n == len(rows)
    return rows


def test_coding_transcript_blocks_and_thick_region(tmp_path: Path) -> None:
    t1 = next(r for r in _bed(tmp_path) if r[3] == "T1")
    # GTF 1-based closed → BED 0-based half-open; exons sorted.
    assert t1[:6] == ["chr1", "99", "500", "T1", "0", "+"]
    assert (t1[6], t1[7]) == ("149", "453")  # CDS start .. stop codon end
    assert t1[9:] == ["2", "101,100,", "0,301,"]


def test_non_coding_transcript_has_empty_thick_region(tmp_path: Path) -> None:
    nc = next(r for r in _bed(tmp_path) if r[3] == "NC1")
    assert nc[1:3] == ["999", "1300"] and nc[5] == "-"
    assert nc[6] == nc[7] == "999"


def test_mixed_chromosome_transcript_skipped_and_output_sorted(tmp_path: Path) -> None:
    rows = _bed(tmp_path)
    assert [r[3] for r in rows] == ["T1", "NC1", "T2"]  # chr1 by start, then chr10


def test_gzipped_gtf(tmp_path: Path) -> None:
    assert [r[3] for r in _bed(tmp_path, gz=True)] == ["T1", "NC1", "T2"]


def test_deterministic(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _bed(tmp_path / "a") == _bed(tmp_path / "b")


def test_no_exons_rejected_and_no_partial_file(tmp_path: Path) -> None:
    gtf = tmp_path / "g.gtf"
    gtf.write_text(_gtf_line("chr1", "gene", 1, 10, "+", "X"))
    out = tmp_path / "o" / "genes.bed12"
    with pytest.raises(ToolValidationError):
        convert_gtf_to_bed12(str(gtf), str(out))
    assert not out.exists()


def test_missing_gtf_rejected(tmp_path: Path) -> None:
    with pytest.raises(ToolValidationError):
        convert_gtf_to_bed12(str(tmp_path / "nope.gtf"), str(tmp_path / "x.bed"))


def test_no_temp_files_left(tmp_path: Path) -> None:
    _bed(tmp_path)
    assert os.listdir(tmp_path / "out") == ["genes.bed12"]


class TestEnsureGeneModelBed:
    def test_genome_bed_wins(self, tmp_path: Path) -> None:
        derived = tmp_path / "d.bed12"
        assert ensure_gene_model_bed("/ref/genes.bed", "/ref/g.gtf", str(derived)) == (
            "/ref/genes.bed"
        )
        assert not derived.exists()

    def test_derived_once_and_reused(self, tmp_path: Path) -> None:
        gtf = tmp_path / "g.gtf"
        gtf.write_text(GTF)
        derived = tmp_path / "gene_model" / "genes.bed12"
        assert ensure_gene_model_bed(None, str(gtf), str(derived)) == str(derived)
        first = derived.read_text()
        gtf.write_text(_gtf_line("chr9", "exon", 1, 10, "+", "OTHER"))
        assert ensure_gene_model_bed("", str(gtf), str(derived)) == str(derived)
        assert derived.read_text() == first  # not regenerated
