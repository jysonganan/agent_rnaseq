"""VizAgent — Streamlit data preparation and UCSC track generation."""

from __future__ import annotations

from typing import Any, TypedDict

from src.agents.specialists._base import BaseSpecialistAgent, _make_stage_output
from src.db.enums import ArtifactType, StageName
from src.tools.base import ToolExecutionError
from src.tools.viz.streamlit_prep import StreamlitDataPrepInput, prepare_streamlit_data
from src.tools.viz.ucsc_tracks import UCSCTrackInput, generate_ucsc_tracks


class VizStageInput(TypedDict):
    run_id: str
    de_results_dir: str | None
    gsea_results_dir: str | None
    qc_metrics_path: str | None
    bam_paths: list[str]
    genome_build: str
    output_dir: str
    track_name_prefix: str
    chrom_sizes_path: str


class VizAgent(BaseSpecialistAgent):
    def __init__(self, db, llm_client=None, dry_run: bool = False, mock_registry=None):
        super().__init__(StageName.visualization, db, llm_client=llm_client, dry_run=dry_run, mock_registry=mock_registry)

    def run(self, stage_input: VizStageInput) -> dict[str, Any]:  # type: ignore[override]
        stage = self._start_stage(stage_input["run_id"], StageName.visualization, "streamlit")
        try:
            streamlit_out = prepare_streamlit_data(
                StreamlitDataPrepInput(
                    run_id=stage_input["run_id"],
                    de_results_dir=stage_input.get("de_results_dir"),
                    gsea_results_dir=stage_input.get("gsea_results_dir"),
                    qc_metrics_path=stage_input.get("qc_metrics_path"),
                    output_dir=stage_input["output_dir"],
                )
            )

            ucsc_out = generate_ucsc_tracks(
                UCSCTrackInput(
                    bam_paths=stage_input["bam_paths"],
                    genome_build=stage_input["genome_build"],
                    output_dir=stage_input["output_dir"],
                    track_name_prefix=stage_input["track_name_prefix"],
                    chrom_sizes_path=stage_input["chrom_sizes_path"],
                )
            )

            self._write_artifact(
                stage.id, stage_input["run_id"], ArtifactType.streamlit_data, streamlit_out.manifest_path
            )
            for bw_path in ucsc_out.bigwig_paths:
                self._write_artifact(stage.id, stage_input["run_id"], ArtifactType.ucsc_track, bw_path)

            tool_version = streamlit_out.tool_version
            self._complete_stage(stage, tool_version=tool_version)
            return _make_stage_output("visualization", "completed", streamlit_out.model_dump(), tool_version)

        except ToolExecutionError as exc:
            self._fail_stage(stage, str(exc))
            raise
