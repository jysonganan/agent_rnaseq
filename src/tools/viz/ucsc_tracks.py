"""UCSC genome browser track generation tool — stub (implemented in a future task)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UCSCTrackInput(BaseModel):
    bam_paths: list[str] = Field(..., min_length=1)
    genome_build: str
    output_dir: str
    track_name_prefix: str
    chrom_sizes_path: str


class UCSCTrackOutput(BaseModel):
    bigwig_paths: list[str]
    track_hub_path: str
    tool_version: str | None = None


def generate_ucsc_tracks(inp: UCSCTrackInput) -> UCSCTrackOutput:
    raise NotImplementedError("generate_ucsc_tracks is not yet implemented")
