"""Pure text parsers for variant calling tool outputs.

All functions are side-effect free — they take raw string content
and return structured data.  File I/O happens in the tool modules.
"""

from __future__ import annotations


def parse_vcf_variant_counts(text: str) -> dict:  # type: ignore[type-arg]
    """Count total, PASS, and filtered variants in VCF text.

    Lines starting with ``#`` are header/metadata and are skipped.
    A variant with ``FILTER`` equal to ``PASS`` or ``.`` (unfiltered) is
    counted as passing; all other filter values count as filtered.

    Returns a dict with ``total_count``, ``pass_count``, and
    ``filtered_count``.
    """
    total = 0
    pass_count = 0
    filtered_count = 0

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        total += 1
        filter_field = parts[6].strip()
        if filter_field in ("PASS", "."):
            pass_count += 1
        else:
            filtered_count += 1

    return {
        "total_count": total,
        "pass_count": pass_count,
        "filtered_count": filtered_count,
    }
