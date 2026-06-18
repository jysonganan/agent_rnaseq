"""DEAgent — DESeq2 differential expression analysis."""

from __future__ import annotations

import uuid as _uuid
from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.db.models.results import DEGResult as DEGResultRow
from src.tools.base import ToolExecutionError
from src.tools.de.deseq2 import DEContrast, DESeq2Input, run_deseq2
from src.tools.de.parsers import parse_deseq2_results


class DEStageInput(TypedDict):
    run_id: str
    counts_matrix_path: str
    sample_metadata_path: str
    contrasts: list[dict]   # [{name, numerator, denominator}, ...]
    output_dir: str
    alpha: float
    lfc_threshold: float
    r_script_path: str


def _read_deseq2_file(path: str) -> str:
    """Read a DESeq2 results CSV. Patched in unit tests."""
    with open(path) as fh:
        return fh.read()


class DEAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(StageName.differential_expression, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry)

    def run(self, stage_input: DEStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(
            stage_input["run_id"], StageName.differential_expression, "deseq2"
        )
        try:
            contrasts = [
                DEContrast(name=c["name"], numerator=c["numerator"], denominator=c["denominator"])
                for c in stage_input["contrasts"]
            ]
            deseq2_out = run_deseq2(
                DESeq2Input(
                    counts_matrix_path=stage_input["counts_matrix_path"],
                    sample_metadata_path=stage_input["sample_metadata_path"],
                    contrasts=contrasts,
                    output_dir=stage_input["output_dir"],
                    alpha=stage_input["alpha"],
                    lfc_threshold=stage_input["lfc_threshold"],
                    r_script_path=stage_input["r_script_path"],
                )
            )

            run_uuid = _uuid.UUID(stage_input["run_id"])
            for contrast_name, results_path in deseq2_out.results_paths.items():
                csv_text = _read_deseq2_file(results_path)
                parsed = parse_deseq2_results(csv_text)
                for deg in parsed:
                    self.db.add(
                        DEGResultRow(
                            stage_id=stage.id,
                            run_id=run_uuid,
                            contrast=contrast_name,
                            gene_id=deg.gene_id,
                            basemean=deg.base_mean,
                            log2_fold_change=deg.log2_fold_change,
                            lfcse=deg.lfc_se,
                            stat=deg.stat,
                            pvalue=deg.pvalue,
                            padj=deg.padj,
                        )
                    )
                self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.de_table, results_path)

            self.db.flush()
            tool_version = deseq2_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("differential_expression", "completed", deseq2_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
