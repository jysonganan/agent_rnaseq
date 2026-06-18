"""Pure text/dict parsers for quantification tool outputs.

All functions are side-effect free — they take raw string/dict content
and return structured data.  File I/O happens in the tool modules.
"""

from __future__ import annotations

# ── HTSeq ──────────────────────────────────────────────────────────────────────


def parse_htseq_counts(text: str) -> dict:  # type: ignore[type-arg]
    """Parse ``htseq-count`` stdout into count statistics.

    Lines starting with ``__`` are HTSeq special categories (no_feature,
    ambiguous, etc.).  All other tab-separated lines are gene count rows.

    Returns a dict with ``counted_reads``, ``no_feature_reads``,
    ``ambiguous_reads``, and ``total_reads`` (sum of all categories).
    """
    counted = 0
    no_feature = 0
    ambiguous = 0
    too_low_aqual = 0
    not_aligned = 0
    alignment_not_unique = 0

    _SPECIAL: dict[str, str] = {
        "__no_feature": "no_feature",
        "__ambiguous": "ambiguous",
        "__too_low_aQual": "too_low_aqual",
        "__not_aligned": "not_aligned",
        "__alignment_not_unique": "alignment_not_unique",
    }

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        key, value_str = parts[0].strip(), parts[1].strip()
        try:
            count = int(value_str)
        except ValueError:
            continue

        if key in _SPECIAL:
            tag = _SPECIAL[key]
            if tag == "no_feature":
                no_feature = count
            elif tag == "ambiguous":
                ambiguous = count
            elif tag == "too_low_aqual":
                too_low_aqual = count
            elif tag == "not_aligned":
                not_aligned = count
            elif tag == "alignment_not_unique":
                alignment_not_unique = count
        elif not key.startswith("__"):
            counted += count

    total = counted + no_feature + ambiguous + too_low_aqual + not_aligned + alignment_not_unique
    return {
        "counted_reads": counted,
        "no_feature_reads": no_feature,
        "ambiguous_reads": ambiguous,
        "too_low_aqual_reads": too_low_aqual,
        "not_aligned_reads": not_aligned,
        "alignment_not_unique_reads": alignment_not_unique,
        "total_reads": total,
    }


# ── Salmon ─────────────────────────────────────────────────────────────────────


def parse_salmon_meta_info(data: dict) -> dict:  # type: ignore[type-arg]
    """Extract mapping rate and inferred library type from Salmon ``meta_info.json``.

    Handles key name variations across Salmon versions:
    - mapping rate: ``mappingRate`` (>= 0.14) or ``percent_mapped``
    - library type: ``inferred_library_type`` or first entry of ``library_types``
    """
    mapping_rate = float(data.get("mappingRate") or data.get("percent_mapped") or 0.0)

    inferred_lib_type = (
        data.get("inferred_library_type")
        or ((data.get("library_types") or ["unknown"])[0])
        or "unknown"
    )

    return {
        "mapping_rate": mapping_rate,
        "inferred_lib_type": str(inferred_lib_type),
    }
