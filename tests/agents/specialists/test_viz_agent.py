"""Tests for VizAgent."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.viz_agent import VizAgent, VizStageInput
from src.db.enums import ArtifactType, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.viz.streamlit_prep import StreamlitDataPrepOutput
from src.tools.viz.ucsc_tracks import UCSCTrackOutput
from tests.agents.specialists.conftest import RUN_ID

_STREAMLIT_OUT = StreamlitDataPrepOutput(
    output_dir="/out/viz",
    manifest_path="/out/viz/manifest.json",
    tool_version="streamlit 1.35.0",
)

_UCSC_OUT = UCSCTrackOutput(
    bigwig_paths=["/out/viz/sample.bw"],
    track_hub_path="/out/viz/trackDb.txt",
    tool_version=None,
)


def _base_input(**kwargs) -> VizStageInput:
    return VizStageInput(
        run_id=RUN_ID,
        de_results_dir="/out/de",
        gsea_results_dir="/out/gsea",
        qc_metrics_path=None,
        bam_paths=["/out/align/sample.bam"],
        genome_build="hg38",
        output_dir="/out/viz",
        track_name_prefix="sample",
        chrom_sizes_path="/ref/hg38.chrom.sizes",
        **kwargs,
    )


@patch("src.agents.specialists.viz_agent.generate_ucsc_tracks", return_value=_UCSC_OUT)
@patch("src.agents.specialists.viz_agent.prepare_streamlit_data", return_value=_STREAMLIT_OUT)
class TestVizAgentSuccess:
    def test_stage_status_completed(self, mock_streamlit, mock_ucsc, db) -> None:
        VizAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_streamlit, mock_ucsc, db) -> None:
        VizAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "streamlit 1.35.0"

    def test_streamlit_artifact_written(self, mock_streamlit, mock_ucsc, db) -> None:
        VizAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.streamlit_data in types

    def test_ucsc_track_artifact_written(self, mock_streamlit, mock_ucsc, db) -> None:
        VizAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.ucsc_track in types


@patch("src.agents.specialists.viz_agent.generate_ucsc_tracks", return_value=_UCSC_OUT)
@patch("src.agents.specialists.viz_agent.prepare_streamlit_data")
class TestVizAgentFailure:
    def test_tool_error_fails_stage(self, mock_streamlit, mock_ucsc, db) -> None:
        mock_streamlit.side_effect = ToolExecutionError("streamlit", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            VizAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed
