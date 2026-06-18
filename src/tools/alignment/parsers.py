"""Pure text parsers for STAR and samtools outputs.

All functions are side-effect free — they take raw string content
and return structured data.  File I/O happens in the tool modules.
"""

from __future__ import annotations

import contextlib
import re

# ── STAR ───────────────────────────────────────────────────────────────────────


def parse_star_log_final(text: str) -> dict:  # type: ignore[type-arg]
    """Parse STAR ``Log.final.out`` content.

    Returns a dict with keys:
        ``total_reads`` (int), ``uniquely_mapped_pct`` (float),
        ``multi_mapped_pct`` (float), ``unmapped_pct`` (float — sum of all
        unmapped categories).

    Lines that don't contain `` | `` or have unparseable values are skipped.
    """
    result: dict[str, object] = {
        "total_reads": 0,
        "uniquely_mapped_pct": 0.0,
        "multi_mapped_pct": 0.0,
        "unmapped_pct": 0.0,
    }

    for line in text.splitlines():
        if "|" not in line:
            continue
        key, _, value = line.partition("|")
        key = key.strip()
        value = value.strip()

        if key == "Number of input reads":
            with contextlib.suppress(ValueError):
                result["total_reads"] = int(value)

        elif key == "Uniquely mapped reads %":
            m = re.search(r"([\d.]+)%", value)
            if m:
                result["uniquely_mapped_pct"] = float(m.group(1))

        elif key == "% of reads mapped to multiple loci":
            m = re.search(r"([\d.]+)%", value)
            if m:
                result["multi_mapped_pct"] = float(m.group(1))

        elif key.startswith("% of reads unmapped"):
            m = re.search(r"([\d.]+)%", value)
            if m:
                current = float(result.get("unmapped_pct", 0.0))  # type: ignore[arg-type]
                result["unmapped_pct"] = round(current + float(m.group(1)), 6)

    return result


# ── samtools ───────────────────────────────────────────────────────────────────

_FLAGSTAT_PATTERNS: dict[str, str] = {
    "total": r"^(\d+) \+ \d+ in total",
    "secondary": r"^(\d+) \+ \d+ secondary",
    "supplementary": r"^(\d+) \+ \d+ supplementary",
    "duplicates": r"^(\d+) \+ \d+ duplicates",
    "mapped": r"^(\d+) \+ \d+ mapped",
    "paired": r"^(\d+) \+ \d+ paired in sequencing",
    "read1": r"^(\d+) \+ \d+ read1",
    "read2": r"^(\d+) \+ \d+ read2",
    "properly_paired": r"^(\d+) \+ \d+ properly paired",
    "with_itself_and_mate_mapped": r"^(\d+) \+ \d+ with itself and mate mapped",
    "singletons": r"^(\d+) \+ \d+ singletons",
    "mate_diff_chr": r"^(\d+) \+ \d+ with mate mapped to a different chr$",
    "mate_diff_chr_mapq5": r"^(\d+) \+ \d+ with mate mapped to a different chr \(mapQ>=5\)",
}


def parse_samtools_flagstat(text: str) -> dict:  # type: ignore[type-arg]
    """Parse ``samtools flagstat`` stdout into a structured dict.

    Each recognized line produces a ``{key: int}`` entry.  Lines that also
    contain a percentage (e.g. ``mapped (98.00% : N/A)``) additionally
    produce ``{key + "_pct": float}``.
    """
    result: dict[str, object] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for key, pattern in _FLAGSTAT_PATTERNS.items():
            m = re.match(pattern, line)
            if m:
                result[key] = int(m.group(1))
                pct_m = re.search(r"\(([\d.]+)%", line)
                if pct_m:
                    result[f"{key}_pct"] = float(pct_m.group(1))
                break

    return result
