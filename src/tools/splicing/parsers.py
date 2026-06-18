"""Pure text parsers for splicing analysis tool outputs.

All functions are side-effect free — they take raw string content
and return structured data.  File I/O happens in the tool modules.
"""

from __future__ import annotations

import contextlib


def parse_rmats_summary(text: str) -> dict[str, int]:
    """Parse an rMATS ``summary.txt`` into ``{event_type: significant_count}``.

    Expected format (tab-separated, first row is header)::

        EventType    TotalEvents    SignificantEvents
        SE           1500           120
        ...

    Lines starting with ``#`` or whose first column is ``EventType`` are
    treated as headers and skipped.
    """
    result: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3 or parts[0] == "EventType":
            continue
        event_type = parts[0].strip()
        with contextlib.suppress(ValueError):
            result[event_type] = int(parts[2].strip())
    return result


def count_rmats_significant(jc_text: str, fdr_threshold: float = 0.05) -> int:
    """Count significant events in a ``*.MATS.JC.txt`` file.

    The FDR value is at column index 19 (0-based) in the rMATS JC output.
    Header rows are identified by a non-integer first column and skipped.

    Returns the number of rows where ``FDR < fdr_threshold``.
    """
    count = 0
    for line in jc_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        # Skip header — first column is not an integer
        try:
            int(parts[0])
        except ValueError:
            continue
        if len(parts) <= 19:
            continue
        try:
            fdr = float(parts[19])
            if fdr < fdr_threshold:
                count += 1
        except ValueError:
            pass
    return count
