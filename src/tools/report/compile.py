"""Report compilation tool — stub (implemented in a future task)."""

from __future__ import annotations

from pydantic import BaseModel


class ReportInput(BaseModel):
    run_id: str
    run_name: str
    qc_summary: dict | None = None
    de_summary: dict | None = None
    gsea_summary: dict | None = None
    artifact_paths: dict[str, str] = {}
    output_dir: str
    template_path: str


class ReportOutput(BaseModel):
    html_report_path: str
    markdown_report_path: str
    tool_version: str | None = None


def compile_report(inp: ReportInput) -> ReportOutput:
    raise NotImplementedError("compile_report is not yet implemented")
