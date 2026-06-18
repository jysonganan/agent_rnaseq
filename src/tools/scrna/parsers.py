"""Pure text parsers for CellRanger output files.

All functions are side-effect free — they take raw string content and return
structured data.  File I/O happens in the tool module (cellranger.py).
"""

from __future__ import annotations

import csv
import io
import re

# Maps CellRanger metric display names → normalised dict keys.
_METRIC_MAP: dict[str, str] = {
    "Estimated Number of Cells": "estimated_cells",
    "Mean Reads per Cell": "mean_reads_per_cell",
    "Median Genes per Cell": "median_genes_per_cell",
    "Number of Reads": "number_of_reads",
    "Valid Barcodes": "valid_barcodes",
    "Sequencing Saturation": "sequencing_saturation",
    "Median UMI Counts per Cell": "median_umi_counts_per_cell",
    "Total Genes Detected": "total_genes_detected",
}


def _coerce_value(raw: str) -> int | float | str:
    """Strip formatting characters and coerce to int, float, or str."""
    cleaned = raw.strip().rstrip("%").replace(",", "")
    try:
        as_int = int(cleaned)
        return as_int
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return raw.strip()


def parse_web_summary(text: str) -> dict[str, int | float | str]:
    """Parse a CellRanger ``metrics_summary.csv`` into a normalised stats dict.

    The file uses metric names as column headers with a single data row.
    Values with commas (e.g. "2,700") and percent signs are cleaned before
    numeric coercion.

    Returns a dict whose keys follow the :data:`_METRIC_MAP` mappings for
    well-known metrics, with all remaining metrics stored under a lowercase,
    underscore-separated key derived from the header name.
    """
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        result: dict[str, int | float | str] = {}
        for header, raw_value in row.items():
            key = _METRIC_MAP.get(header, re.sub(r"\s+", "_", header).lower())
            result[key] = _coerce_value(raw_value)
        return result
    return {}
