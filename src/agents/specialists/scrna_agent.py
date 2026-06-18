"""scRNAAgent — CellRanger count + Scanpy clustering pipeline."""

from __future__ import annotations

import uuid as _uuid
from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.db.models.results import ScRNAClusterResult
from src.tools.base import ToolExecutionError
from src.tools.scrna.cellranger import CellRangerCountInput, run_cellranger_count
from src.tools.scrna.scanpy_tool import ScanpyInput, run_scanpy_pipeline


class ScRNAStageInput(TypedDict):
    run_id: str
    sample_id: str
    fastq_dirs: list[str]
    sample_name: str
    transcriptome_path: str
    output_dir: str
    script_path: str


class scRNAAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(StageName.scrna_seq, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry)

    def run(self, stage_input: ScRNAStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(
            stage_input["run_id"], StageName.scrna_seq, "cellranger", sample_id=stage_input["sample_id"]
        )
        try:
            cr_out = run_cellranger_count(
                CellRangerCountInput(
                    fastq_dirs=stage_input["fastq_dirs"],
                    sample_name=stage_input["sample_name"],
                    transcriptome_path=stage_input["transcriptome_path"],
                    output_dir=stage_input["output_dir"],
                )
            )

            scanpy_out = run_scanpy_pipeline(
                ScanpyInput(
                    matrix_dir=cr_out.filtered_matrix_dir,
                    output_dir=stage_input["output_dir"] + "/scanpy",
                    script_path=stage_input["script_path"],
                )
            )

            run_uuid = _uuid.UUID(stage_input["run_id"])
            sample_uuid = _uuid.UUID(stage_input["sample_id"])
            n_clusters = scanpy_out.cluster_summary.n_clusters

            for cluster_id_str, n_cells in scanpy_out.cluster_summary.cells_per_cluster.items():
                self.db.add(
                    ScRNAClusterResult(
                        stage_id=stage.id,
                        run_id=run_uuid,
                        sample_id=sample_uuid,
                        n_clusters=n_clusters,
                        cluster_id=int(cluster_id_str),
                        n_cells=n_cells,
                    )
                )

            self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.scrna_h5ad, scanpy_out.h5ad_path)
            self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.scrna_umap, scanpy_out.umap_plot_path)
            self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.marker_genes, scanpy_out.marker_genes_path)

            self.db.flush()
            tool_version = cr_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("scrna_seq", "completed", scanpy_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
