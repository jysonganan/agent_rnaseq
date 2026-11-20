"""UCSC genome browser tracks: deepTools bamCoverage bigWigs + a track hub.

See ``docs/specs/tool_contracts.md`` §9.
"""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field

from src.tools.base import ToolValidationError, detect_version, run_subprocess, tool_call

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


class UCSCTrackInput(BaseModel):
    bam_paths: list[str] = Field(..., min_length=1)
    genome_build: str = Field(..., pattern=r"^[A-Za-z0-9_.-]+$")
    output_dir: str
    track_name_prefix: str
    chrom_sizes_path: str | None = None
    bin_size: int = Field(default=10, ge=1, le=10000)
    threads: int = Field(default=4, ge=1, le=256)


class UCSCTrackOutput(BaseModel):
    bigwig_paths: list[str]
    track_hub_path: str
    tool_version: str | None = None


def _track_id(prefix: str, bam_path: str) -> str:
    stem = os.path.basename(bam_path)
    for ext in (".bam", "_sorted"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
    return _SAFE.sub("_", f"{prefix}_{stem}").strip("_")[:120]


@tool_call
def generate_ucsc_tracks(inp: UCSCTrackInput) -> UCSCTrackOutput:
    os.makedirs(inp.output_dir, exist_ok=True)
    version = detect_version(["bamCoverage", "--version"], "bamCoverage")

    track_ids: list[str] = []
    bigwigs: list[str] = []
    for bam in inp.bam_paths:
        if not os.path.isfile(bam + ".bai") and not os.path.isfile(bam[:-4] + ".bai"):
            raise ToolValidationError("generate_ucsc_tracks", "bam_paths", f"no index for {bam}")
        track_id = _track_id(inp.track_name_prefix, bam)
        if track_id in track_ids:
            raise ToolValidationError("generate_ucsc_tracks", "bam_paths", f"duplicate {track_id}")
        bigwig = os.path.join(inp.output_dir, f"{track_id}.bw")
        run_subprocess(
            [
                "bamCoverage",
                "--bam",
                bam,
                "--outFileName",
                bigwig,
                "--outFileFormat",
                "bigwig",
                "--normalizeUsing",
                "CPM",
                "--binSize",
                str(inp.bin_size),
                "--numberOfProcessors",
                str(inp.threads),
            ],
            tool_name="bamCoverage",
        )
        track_ids.append(track_id)
        bigwigs.append(bigwig)

    hub_name = _SAFE.sub("_", inp.track_name_prefix).strip("_") or "rnaseq"
    with open(os.path.join(inp.output_dir, "hub.txt"), "w") as fh:
        fh.write(
            f"hub {hub_name}\nshortLabel {hub_name}\nlongLabel RNA-seq coverage: {hub_name}\n"
            "genomesFile genomes.txt\nemail none\n"
        )
    with open(os.path.join(inp.output_dir, "genomes.txt"), "w") as fh:
        fh.write(f"genome {inp.genome_build}\ntrackDb {inp.genome_build}/trackDb.txt\n")

    build_dir = os.path.join(inp.output_dir, inp.genome_build)
    os.makedirs(build_dir, exist_ok=True)
    track_db = os.path.join(build_dir, "trackDb.txt")
    with open(track_db, "w") as fh:
        for track_id in track_ids:
            fh.write(
                f"track {track_id}\nbigDataUrl ../{track_id}.bw\nshortLabel {track_id[:17]}\n"
                f"longLabel {track_id} coverage (CPM)\ntype bigWig\nvisibility full\n"
                "autoScale on\n\n"
            )

    return UCSCTrackOutput(bigwig_paths=bigwigs, track_hub_path=track_db, tool_version=version)
