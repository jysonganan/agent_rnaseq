"""Pure text parsers for Reactome GSEA output CSV files.

All functions are side-effect free — they take raw string content and return
structured data.  File I/O happens in the tool module (reactome.py).
"""

from __future__ import annotations

import contextlib
import csv
import io

from pydantic import BaseModel


class GSEAResult(BaseModel):
    pathway_id: str
    pathway_name: str
    nes: float
    pvalue: float
    padj: float


def parse_gsea_results(text: str) -> list[GSEAResult]:
    """Parse a Reactome GSEA results CSV into a list of :class:`GSEAResult` records.

    Expected columns: pathway_id, pathway_name, NES, pvalue, padj.
    Rows with unparseable numeric values are skipped.
    """
    results: list[GSEAResult] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        with contextlib.suppress(ValueError, KeyError):
            results.append(
                GSEAResult(
                    pathway_id=row.get("pathway_id", ""),
                    pathway_name=row.get("pathway_name", ""),
                    nes=float(row.get("NES", "")),
                    pvalue=float(row.get("pvalue", "")),
                    padj=float(row.get("padj", "")),
                )
            )
    return results


def count_significant_pathways(
    results: list[GSEAResult],
    padj_threshold: float = 0.05,
) -> int:
    """Return the number of pathways with ``padj < padj_threshold``."""
    return sum(1 for r in results if r.padj < padj_threshold)
