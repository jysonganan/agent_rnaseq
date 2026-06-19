"""ReportAgent — final HTML/Markdown report assembly."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.tools.base import ToolExecutionError
from src.tools.report.compile import ReportInput, compile_report


class ReportStageInput(TypedDict):
    run_id: str
    run_name: str
    qc_summary: dict | None
    de_summary: dict | None
    gsea_summary: dict | None
    artifact_paths: dict[str, str]
    output_dir: str
    template_path: str


class ReportAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.report,
            db,
            llm_client=llm_client,
            dry_run=dry_run,
            mock_registry=mock_registry,
        )

    def run(self, stage_input: ReportStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(stage_input["run_id"], StageName.report, "report_compiler")
        try:
            report_out = compile_report(
                ReportInput(
                    run_id=stage_input["run_id"],
                    run_name=stage_input["run_name"],
                    qc_summary=stage_input.get("qc_summary"),
                    de_summary=stage_input.get("de_summary"),
                    gsea_summary=stage_input.get("gsea_summary"),
                    artifact_paths=stage_input.get("artifact_paths", {}),
                    output_dir=stage_input["output_dir"],
                    template_path=stage_input["template_path"],
                )
            )

            self._write_artifact(
                stage.id,
                stage_input["run_id"],
                ArtifactType.html_report,
                report_out.html_report_path,
            )

            tool_version = report_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("report", "completed", report_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
