"""Pure text/dict parsers for QC tool outputs.

All functions are side-effect free — they take raw string/dict content
and return structured data.  File I/O happens in the tool modules.
"""

from __future__ import annotations

import re

# ── FastQC ─────────────────────────────────────────────────────────────────────


def parse_fastqc_summary(text: str) -> dict[str, str]:
    """Parse the ``summary.txt`` content from a FastQC ZIP.

    Each line is: ``STATUS\\tModule Name\\tFilename``

    Returns ``{module_name: status}`` e.g. ``{"Basic Statistics": "PASS"}``.
    Skips blank lines and lines that don't have exactly three tab-separated
    fields so the function is robust to trailing newlines.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, module = parts[0].strip(), parts[1].strip()
        if status and module:
            result[module] = status
    return result


# ── MultiQC ────────────────────────────────────────────────────────────────────


def parse_multiqc_general_stats(data: dict) -> dict:  # type: ignore[type-arg]
    """Parse ``multiqc_general_stats.json`` content into sample → metric → value.

    MultiQC writes a flat dict ``{sample: {metric: value}}``.  We return it
    as-is after stripping any ``None`` metric values.
    """
    parsed: dict[str, dict] = {}  # type: ignore[type-arg]
    for sample, metrics in data.items():
        if not isinstance(metrics, dict):
            continue
        parsed[sample] = {k: v for k, v in metrics.items() if v is not None}
    return parsed


# ── RSeQC ──────────────────────────────────────────────────────────────────────

_RD_GROUP_RE = re.compile(r"^(\S+(?:'\S*)?)\s+\d+\s+(\d+)\s+[\d.]+\s*$")


def parse_rseqc_read_distribution(text: str) -> dict[str, int]:
    """Parse ``read_distribution.py`` stdout into ``{region: tag_count}``.

    Handles lines from the "Group" table:
        ``CDS_Exons    34560000    38000000    1099.54``
    The second integer column is ``Tag_count``.

    Also captures the summary header lines:
        ``Total Reads                   45000000``
    Keys for those are ``"Total_Reads"``, ``"Total_Tags"``,
    ``"Total_Assigned_Tags"``.
    """
    result: dict[str, int] = {}

    # Header summary lines
    _SUMMARY_KEYS = {
        "Total Reads": "Total_Reads",
        "Total Tags": "Total_Tags",
        "Total Assigned Tags": "Total_Assigned_Tags",
    }
    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("Group") or line_stripped.startswith("="):
            continue
        # Check for summary key
        matched_summary = False
        for raw_key, out_key in _SUMMARY_KEYS.items():
            if line_stripped.startswith(raw_key):
                parts = line_stripped.split()
                if parts and parts[-1].isdigit():
                    result[out_key] = int(parts[-1])
                matched_summary = True
                break
        if matched_summary:
            continue
        # Group table rows (two or more integer columns)
        cols = line_stripped.split()
        if len(cols) >= 3 and cols[1].isdigit() and cols[2].isdigit():
            region = cols[0]
            tag_count = int(cols[2])
            result[region] = tag_count

    return result


def parse_rseqc_infer_experiment(text: str) -> dict:  # type: ignore[type-arg]
    """Parse ``infer_experiment.py`` stdout.

    Returns:
        ``library_type``: "PairEnd" | "SingleEnd" | "Unknown"
        ``undetermined``: float fraction
        ``sense``: float fraction (forward strand)
        ``antisense``: float fraction (reverse strand)
    """
    result: dict[str, object] = {
        "library_type": "Unknown",
        "undetermined": 0.0,
        "sense": 0.0,
        "antisense": 0.0,
    }
    for line in text.splitlines():
        line = line.strip()
        if "PairEnd" in line or "Pair-End" in line or "pair-end" in line.lower():
            result["library_type"] = "PairEnd"
        elif "SingleEnd" in line or "Single-End" in line or "single-end" in line.lower():
            result["library_type"] = "SingleEnd"

        m = re.search(r"failed to determine[:\s]+([\d.]+)", line, re.IGNORECASE)
        if m:
            result["undetermined"] = float(m.group(1))
            continue

        # Sense strand: "1++,1--,2+-,2-+" pattern or "sense" label
        m_sense = re.search(r'(?:1\+\+,1--,2\+-,2-\+|"sense")\D+([\d.]+)', line, re.IGNORECASE)
        if m_sense:
            result["sense"] = float(m_sense.group(1))
            continue

        # Antisense strand
        m_anti = re.search(r'(?:1\+-,1-\+,2\+\+,2--|"antisense")\D+([\d.]+)', line, re.IGNORECASE)
        if m_anti:
            result["antisense"] = float(m_anti.group(1))

    return result
