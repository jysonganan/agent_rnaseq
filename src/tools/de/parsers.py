"""Pure text parsers for DESeq2 output CSV files.

All functions are side-effect free — they take raw string content and return
structured data.  File I/O happens in the tool module (deseq2.py).
"""

from __future__ import annotations

import csv
import io

from pydantic import BaseModel


class DEGResult(BaseModel):
    gene_id: str
    base_mean: float | None
    log2_fold_change: float | None
    lfc_se: float | None
    stat: float | None
    pvalue: float | None
    padj: float | None


class DEContrastSummary(BaseModel):
    total_genes: int
    upregulated: int
    downregulated: int
    not_significant: int


def _parse_float(value: str) -> float | None:
    """Return float or None for missing/NA values."""
    if value.strip() in ("", "NA", "NaN", "nan", "Inf", "-Inf", "inf", "-inf"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_deseq2_results(text: str) -> list[DEGResult]:
    """Parse a DESeq2 results CSV into a list of :class:`DEGResult` records.

    Expected columns: gene_id, baseMean, log2FoldChange, lfcSE, stat, pvalue, padj.
    NA values in numeric columns are stored as ``None``.
    """
    results: list[DEGResult] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        results.append(
            DEGResult(
                gene_id=row.get("gene_id", ""),
                base_mean=_parse_float(row.get("baseMean", "")),
                log2_fold_change=_parse_float(row.get("log2FoldChange", "")),
                lfc_se=_parse_float(row.get("lfcSE", "")),
                stat=_parse_float(row.get("stat", "")),
                pvalue=_parse_float(row.get("pvalue", "")),
                padj=_parse_float(row.get("padj", "")),
            )
        )
    return results


def compute_contrast_summary(
    results: list[DEGResult],
    alpha: float = 0.05,
) -> DEContrastSummary:
    """Compute upregulated / downregulated / not-significant counts.

    A gene is significant if ``padj < alpha``.  Among significant genes,
    those with ``log2FoldChange > 0`` are upregulated; ``< 0`` downregulated.
    Genes with NA padj (or lfc) are counted as not significant.
    """
    upregulated = 0
    downregulated = 0
    for r in results:
        if r.padj is not None and r.padj < alpha:
            if r.log2_fold_change is not None and r.log2_fold_change > 0:
                upregulated += 1
            elif r.log2_fold_change is not None and r.log2_fold_change < 0:
                downregulated += 1
    not_significant = len(results) - upregulated - downregulated
    return DEContrastSummary(
        total_genes=len(results),
        upregulated=upregulated,
        downregulated=downregulated,
        not_significant=not_significant,
    )
