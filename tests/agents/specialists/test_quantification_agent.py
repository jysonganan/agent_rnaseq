"""Tests for QuantificationAgent — tool selection and DB writes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.quantification_agent import QuantificationAgent, QuantStageInput
from src.db.enums import ArtifactType, StageStatus
from src.db.models.run import Artifact, PipelineStage
from src.tools.base import ToolExecutionError
from src.tools.quantification.htseq import HTSeqOutput
from src.tools.quantification.rsem import RSEMOutput
from src.tools.quantification.salmon import SalmonQuantOutput
from tests.agents.specialists.conftest import RUN_ID, SAMPLE_ID

_HTSEQ_OUT = HTSeqOutput(
    counts_path="/out/quant/counts.tsv",
    total_reads=1_000_000,
    counted_reads=850_000,
    no_feature_reads=100_000,
    ambiguous_reads=50_000,
    tool_version="HTSeq 2.0.2",
)

_SALMON_OUT = SalmonQuantOutput(
    quant_sf_path="/out/quant/quant.sf",
    lib_format_counts_path="/out/quant/lib_format_counts.json",
    meta_info_path="/out/quant/aux_info/meta_info.json",
    eq_classes_path=None,
    inferred_lib_type="IU",
    mapping_rate=85.2,
    tool_version="Salmon 1.10.1",
)

_RSEM_OUT = RSEMOutput(
    genes_results_path="/out/quant/rsem.genes.results",
    isoforms_results_path="/out/quant/rsem.isoforms.results",
    stat_dir="/out/quant/rsem.stat",
    tool_version="RSEM 1.3.3",
)


def _base_input(method: str = "star_htseq", **kwargs) -> QuantStageInput:
    return QuantStageInput(
        run_id=RUN_ID,
        sample_id=SAMPLE_ID,
        quantification_method=method,
        output_dir="/out/quant",
        bam_path="/out/align/sample.bam",
        gtf_path="/ref/genes.gtf",
        fastq_r1="/data/sample_R1.fastq.gz",
        fastq_r2="/data/sample_R2.fastq.gz",
        index_path="/ref/salmon_index",
        rsem_reference="/ref/rsem_index",
        **kwargs,
    )


class TestQuantificationMethodSelection:
    @patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_HTSEQ_OUT)
    def test_star_htseq_uses_htseq(self, mock_htseq, db) -> None:
        QuantificationAgent(db).run(_base_input("star_htseq"))
        mock_htseq.assert_called_once()

    @patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_HTSEQ_OUT)
    @patch("src.agents.specialists.quantification_agent.run_salmon_quant")
    @patch("src.agents.specialists.quantification_agent.run_rsem")
    def test_star_htseq_does_not_call_salmon_or_rsem(self, mock_rsem, mock_salmon, mock_htseq, db) -> None:
        QuantificationAgent(db).run(_base_input("star_htseq"))
        mock_salmon.assert_not_called()
        mock_rsem.assert_not_called()

    @patch("src.agents.specialists.quantification_agent.run_salmon_quant", return_value=_SALMON_OUT)
    def test_salmon_method_uses_salmon(self, mock_salmon, db) -> None:
        QuantificationAgent(db).run(_base_input("salmon"))
        mock_salmon.assert_called_once()

    @patch("src.agents.specialists.quantification_agent.run_rsem", return_value=_RSEM_OUT)
    def test_rsem_method_uses_rsem(self, mock_rsem, db) -> None:
        QuantificationAgent(db).run(_base_input("rsem"))
        mock_rsem.assert_called_once()


@patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_HTSEQ_OUT)
class TestQuantificationDBWrites:
    def test_stage_completed(self, mock_htseq, db) -> None:
        QuantificationAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.completed

    def test_tool_version_not_null(self, mock_htseq, db) -> None:
        QuantificationAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "HTSeq 2.0.2"

    def test_tool_name_is_htseq(self, mock_htseq, db) -> None:
        QuantificationAgent(db).run(_base_input("star_htseq"))
        stage = db.query(PipelineStage).one()
        assert stage.tool_name == "htseq"

    def test_counts_artifact_written(self, mock_htseq, db) -> None:
        QuantificationAgent(db).run(_base_input())
        artifacts = db.query(Artifact).all()
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.counts_matrix in types

    def test_tool_error_fails_stage(self, mock_htseq, db) -> None:
        mock_htseq.side_effect = ToolExecutionError("htseq", 1, "err", [])
        with pytest.raises(ToolExecutionError):
            QuantificationAgent(db).run(_base_input())
        stage = db.query(PipelineStage).one()
        assert stage.status == StageStatus.failed


@patch("src.agents.specialists.quantification_agent.run_salmon_quant", return_value=_SALMON_OUT)
class TestQuantificationSalmon:
    def test_tool_name_is_salmon(self, mock_salmon, db) -> None:
        QuantificationAgent(db).run(_base_input("salmon"))
        stage = db.query(PipelineStage).one()
        assert stage.tool_name == "salmon"

    def test_tool_version_from_salmon(self, mock_salmon, db) -> None:
        QuantificationAgent(db).run(_base_input("salmon"))
        stage = db.query(PipelineStage).one()
        assert stage.tool_version == "Salmon 1.10.1"
