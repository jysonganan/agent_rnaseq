"""GSEAAgent — Reactome pathway enrichment analysis."""

from __future__ import annotations

import uuid as _uuid
from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.db.models.results import GSEAResult as GSEAResultRow
from src.tools.base import ToolExecutionError
from src.tools.gsea.parsers import parse_gsea_results
from src.tools.gsea.reactome import ReactomeGSEAInput, run_reactome_gsea


class GSEAStageInput(TypedDict):
    run_id: str
    de_results_paths: dict[str, str]  # contrast_name → de_results CSV path
    output_dir: str
    organism: str
    r_script_path: str


def _read_gsea_file(path: str) -> str:
    """Read a GSEA results CSV. Patched in unit tests."""
    with open(path) as fh:
        return fh.read()


class GSEAAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(
            StageName.gsea, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry
        )

    def run(self, stage_input: GSEAStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(stage_input["run_id"], StageName.gsea, "reactome_gsea")
        try:
            run_uuid = _uuid.UUID(stage_input["run_id"])
            last_out = None

            for contrast_name, de_results_path in stage_input["de_results_paths"].items():
                gsea_out = run_reactome_gsea(
                    ReactomeGSEAInput(
                        de_results_path=de_results_path,
                        contrast_name=contrast_name,
                        output_dir=stage_input["output_dir"] + f"/{contrast_name}",
                        organism=stage_input["organism"],
                        r_script_path=stage_input["r_script_path"],
                    )
                )

                csv_text = _read_gsea_file(gsea_out.results_path)
                parsed = parse_gsea_results(csv_text)
                for result in parsed:
                    self.db.add(
                        GSEAResultRow(
                            stage_id=stage.id,
                            run_id=run_uuid,
                            contrast=contrast_name,
                            pathway_id=result.pathway_id,
                            pathway_name=result.pathway_name,
                            nes=result.nes,
                            pvalue=result.pvalue,
                            padj=result.padj,
                        )
                    )
                self._write_artifact(
                    stage.id, stage_input["run_id"], ArtifactType.gsea_result, gsea_out.results_path
                )
                last_out = gsea_out

            self.db.flush()
            tool_version = last_out.tool_version if last_out else None
            self._complete_stage(stage, tool_version=tool_version)
            output_dict = last_out.model_dump() if last_out else {}
            return _make_stage_output("gsea", "completed", output_dict, tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
