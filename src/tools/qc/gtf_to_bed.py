"""Deterministic GTF → BED12 conversion for RSeQC (tool_contracts.md ``convert_gtf_to_bed12``).

RSeQC needs a BED12 gene model. When a genome has no ``bed_annotation_path``, the
``alignment_qc`` stage derives one from the genome's GTF with this converter. It is pure
Python, so it needs no UCSC tools in any image.
"""

from __future__ import annotations

import gzip
import os
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import IO

from src.tools.base import ToolValidationError

_TRANSCRIPT_ID_RE = re.compile(r'transcript_id\s+"([^"]+)"')
_CODING_FEATURES = frozenset({"CDS", "start_codon", "stop_codon"})


@dataclass
class _Transcript:
    chrom: str
    strand: str
    exons: list[tuple[int, int]] = field(default_factory=list)  # 0-based half-open
    coding: list[tuple[int, int]] = field(default_factory=list)
    mixed: bool = False  # exons on several chromosomes/strands → skipped


def _open_text(path: str) -> IO[str]:
    with open(path, "rb") as fh:
        gzipped = fh.read(2) == b"\x1f\x8b"
    if gzipped:
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def _records(fh: IO[str]) -> Iterator[tuple[str, str, int, int, str, str]]:
    for line in fh:
        if not line or line.startswith("#"):
            continue
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 9:
            continue
        feature = cols[2]
        if feature != "exon" and feature not in _CODING_FEATURES:
            continue
        m = _TRANSCRIPT_ID_RE.search(cols[8])
        if m is None:
            continue
        try:
            start, end = int(cols[3]) - 1, int(cols[4])  # GTF 1-based closed → 0-based half-open
        except ValueError:
            continue
        if start < 0 or end <= start:
            continue
        yield cols[0], feature, start, end, cols[6], m.group(1)


def _bed12_line(name: str, t: _Transcript) -> str:
    exons = sorted(set(t.exons))
    tx_start, tx_end = exons[0][0], max(e for _, e in exons)
    if t.coding:
        thick_start = max(tx_start, min(s for s, _ in t.coding))
        thick_end = min(tx_end, max(e for _, e in t.coding))
    else:
        thick_start = thick_end = tx_start  # non-coding
    sizes = ",".join(str(e - s) for s, e in exons) + ","
    starts = ",".join(str(s - tx_start) for s, _ in exons) + ","
    return "\t".join(
        [
            t.chrom,
            str(tx_start),
            str(tx_end),
            name,
            "0",
            t.strand,
            str(thick_start),
            str(thick_end),
            "0",
            str(len(exons)),
            sizes,
            starts,
        ]
    )


def convert_gtf_to_bed12(gtf_path: str, bed_path: str) -> int:
    """Write a BED12 (one line per transcript with exons) from ``gtf_path``; return the count.

    The output is written to a temporary file and renamed, so a partial BED is never read.
    """
    if not os.path.isfile(gtf_path):
        raise ToolValidationError("gtf_to_bed12", "gtf_path", "GTF file not found")

    transcripts: dict[str, _Transcript] = {}
    with _open_text(gtf_path) as fh:
        for chrom, feature, start, end, strand, tid in _records(fh):
            t = transcripts.get(tid)
            if t is None:
                t = transcripts[tid] = _Transcript(chrom=chrom, strand=strand)
            elif t.chrom != chrom or t.strand != strand:
                t.mixed = True
            if feature == "exon":
                t.exons.append((start, end))
            else:
                t.coding.append((start, end))

    rows = [
        (t.chrom, min(s for s, _ in t.exons), tid, _bed12_line(tid, t))
        for tid, t in transcripts.items()
        if t.exons and not t.mixed
    ]
    if not rows:
        raise ToolValidationError("gtf_to_bed12", "gtf_path", "GTF has no transcripts with exons")
    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    out_dir = os.path.dirname(bed_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".genes.", suffix=".bed12.tmp")
    try:
        with os.fdopen(fd, "w") as out:
            for row in rows:
                out.write(row[3] + "\n")
        os.replace(tmp, bed_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return len(rows)


def ensure_gene_model_bed(bed_annotation_path: str | None, gtf_path: str, derived_path: str) -> str:
    """The BED12 RSeQC should use: the genome's own BED, else one derived from the GTF once.

    ``derived_path`` is run-scoped, so later samples of the same run reuse the first
    conversion. Local paths only; the Nextflow backend handles ``s3://`` itself.
    """
    if bed_annotation_path:
        return bed_annotation_path
    if not os.path.isfile(derived_path):
        convert_gtf_to_bed12(gtf_path, derived_path)
    return derived_path
