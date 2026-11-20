"""Deterministic helpers that turn per-sample quantification files into DESeq2 inputs.

See ``docs/specs/tool_contracts.md`` §6 (``build_count_matrix`` / ``write_sample_metadata``).
"""

from __future__ import annotations

import csv
import os
from typing import Literal

from pydantic import BaseModel, Field

from src.tools.base import ToolValidationError

QuantMethod = Literal["star_htseq", "salmon", "rsem"]


class CountMatrixInput(BaseModel):
    sample_count_paths: dict[str, str] = Field(..., min_length=1)
    method: QuantMethod
    output_path: str


class CountMatrixOutput(BaseModel):
    counts_matrix_path: str
    n_genes: int
    n_samples: int


class SampleMetadataInput(BaseModel):
    sample_conditions: dict[str, str] = Field(..., min_length=2)
    output_path: str


def _read_htseq(path: str) -> dict[str, str]:
    counts: dict[str, str] = {}
    with open(path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2 or parts[0].startswith("__"):
                continue
            counts[parts[0]] = parts[1].strip()
    return counts


def _read_header_column(path: str, id_col: str, value_col: str) -> dict[str, str]:
    counts: dict[str, str] = {}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames or []
        if id_col not in fields or value_col not in fields:
            raise ToolValidationError(
                "build_count_matrix",
                "sample_count_paths",
                f"{os.path.basename(path)} lacks required columns {id_col!r}/{value_col!r}",
            )
        for row in reader:
            counts[row[id_col]] = row[value_col]
    return counts


def _read_counts(path: str, method: QuantMethod) -> dict[str, str]:
    if method == "star_htseq":
        return _read_htseq(path)
    if method == "salmon":
        return _read_header_column(path, "Name", "NumReads")
    return _read_header_column(path, "gene_id", "expected_count")


def build_count_matrix(inp: CountMatrixInput) -> CountMatrixOutput:
    """Merge per-sample count files into a gene x sample CSV (first column ``gene_id``)."""
    per_sample: dict[str, dict[str, str]] = {}
    for sample_id, path in inp.sample_count_paths.items():
        if not os.path.isfile(path):
            raise ToolValidationError(
                "build_count_matrix", "sample_count_paths", f"missing counts for {sample_id}"
            )
        per_sample[sample_id] = _read_counts(path, inp.method)

    gene_ids: list[str] = []
    seen: set[str] = set()
    for counts in per_sample.values():
        for gene_id in counts:
            if gene_id not in seen:
                seen.add(gene_id)
                gene_ids.append(gene_id)

    if not gene_ids:
        raise ToolValidationError("build_count_matrix", "sample_count_paths", "no genes found")

    sample_ids = list(per_sample)
    os.makedirs(os.path.dirname(inp.output_path) or ".", exist_ok=True)
    with open(inp.output_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["gene_id", *sample_ids])
        for gene_id in gene_ids:
            writer.writerow([gene_id, *(per_sample[s].get(gene_id, "0") for s in sample_ids)])

    return CountMatrixOutput(
        counts_matrix_path=inp.output_path,
        n_genes=len(gene_ids),
        n_samples=len(sample_ids),
    )


def write_sample_metadata(inp: SampleMetadataInput) -> str:
    """Write the ``sample_id,condition`` CSV DESeq2 uses as colData."""
    for sample_id, condition in inp.sample_conditions.items():
        if not condition:
            raise ToolValidationError(
                "write_sample_metadata", "sample_conditions", f"sample {sample_id} has no condition"
            )
    if len(set(inp.sample_conditions.values())) < 2:
        raise ToolValidationError(
            "write_sample_metadata",
            "sample_conditions",
            "differential expression needs at least two distinct conditions",
        )

    os.makedirs(os.path.dirname(inp.output_path) or ".", exist_ok=True)
    with open(inp.output_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sample_id", "condition"])
        for sample_id, condition in inp.sample_conditions.items():
            writer.writerow([sample_id, condition])
    return inp.output_path
