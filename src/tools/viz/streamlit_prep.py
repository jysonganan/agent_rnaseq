"""Streamlit data preparation tool — stub (implemented in a future task)."""

from __future__ import annotations

from pydantic import BaseModel


class StreamlitDataPrepInput(BaseModel):
    run_id: str
    de_results_dir: str | None = None
    gsea_results_dir: str | None = None
    qc_metrics_path: str | None = None
    output_dir: str


class StreamlitDataPrepOutput(BaseModel):
    output_dir: str
    manifest_path: str
    tool_version: str | None = None


def prepare_streamlit_data(inp: StreamlitDataPrepInput) -> StreamlitDataPrepOutput:
    raise NotImplementedError("prepare_streamlit_data is not yet implemented")
