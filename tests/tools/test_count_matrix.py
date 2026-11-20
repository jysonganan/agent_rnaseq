"""Tests for the DESeq2 input builders (count matrix + sample metadata)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.tools.base import ToolValidationError
from src.tools.de.count_matrix import (
    CountMatrixInput,
    SampleMetadataInput,
    build_count_matrix,
    write_sample_metadata,
)


def _rows(path: str) -> list[list[str]]:
    with open(path) as fh:
        return list(csv.reader(fh))


def test_htseq_merge_fills_missing_genes_with_zero(tmp_path: Path) -> None:
    (tmp_path / "a.tsv").write_text("G1\t5\nG2\t7\n__ambiguous\t3\n")
    (tmp_path / "b.tsv").write_text("G2\t1\nG3\t9\n")
    out = build_count_matrix(
        CountMatrixInput(
            sample_count_paths={"a": str(tmp_path / "a.tsv"), "b": str(tmp_path / "b.tsv")},
            method="star_htseq",
            output_path=str(tmp_path / "m" / "counts.csv"),
        )
    )
    assert (out.n_genes, out.n_samples) == (3, 2)
    assert _rows(out.counts_matrix_path) == [
        ["gene_id", "a", "b"],
        ["G1", "5", "0"],
        ["G2", "7", "1"],
        ["G3", "0", "9"],
    ]


def test_salmon_uses_numreads(tmp_path: Path) -> None:
    (tmp_path / "quant.sf").write_text(
        "Name\tLength\tEffectiveLength\tTPM\tNumReads\nT1\t100\t80\t12.5\t42.0\n"
    )
    out = build_count_matrix(
        CountMatrixInput(
            sample_count_paths={"s": str(tmp_path / "quant.sf")},
            method="salmon",
            output_path=str(tmp_path / "c.csv"),
        )
    )
    assert _rows(out.counts_matrix_path)[1] == ["T1", "42.0"]


def test_rsem_missing_column_rejected(tmp_path: Path) -> None:
    (tmp_path / "g.results").write_text("gene_id\tTPM\nG1\t1.0\n")
    with pytest.raises(ToolValidationError):
        build_count_matrix(
            CountMatrixInput(
                sample_count_paths={"s": str(tmp_path / "g.results")},
                method="rsem",
                output_path=str(tmp_path / "c.csv"),
            )
        )


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(ToolValidationError):
        build_count_matrix(
            CountMatrixInput(
                sample_count_paths={"s": str(tmp_path / "nope")},
                method="star_htseq",
                output_path=str(tmp_path / "c.csv"),
            )
        )


def test_metadata_requires_two_conditions(tmp_path: Path) -> None:
    with pytest.raises(ToolValidationError):
        write_sample_metadata(
            SampleMetadataInput(
                sample_conditions={"a": "x", "b": "x"}, output_path=str(tmp_path / "m.csv")
            )
        )


def test_metadata_written(tmp_path: Path) -> None:
    path = write_sample_metadata(
        SampleMetadataInput(
            sample_conditions={"a": "ctl", "b": "trt"}, output_path=str(tmp_path / "m.csv")
        )
    )
    assert _rows(path) == [["sample_id", "condition"], ["a", "ctl"], ["b", "trt"]]
