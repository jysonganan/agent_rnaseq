"""Tests for the LangGraph StateGraph pipeline router."""

from __future__ import annotations

import pytest
from langgraph.graph import END

from src.agents.router import ALL_PIPELINE_STAGES, _next_stage, build_pipeline_graph
from src.agents.state import RunState


def _state(
    stages: list[str],
    completed: list[str],
    failed: str | None = None,
) -> RunState:
    return RunState(
        run_id="r1",
        run_config={},
        stages=stages,
        completed_stages=completed,
        failed_stage=failed,
        stage_outputs={},
        error_message=None,
        current_stage=None,
    )


class TestAllPipelineStages:
    def test_contains_expected_stages(self) -> None:
        for stage in ("qc", "alignment", "quantification", "variant_calling",
                      "splicing", "differential_expression", "gsea",
                      "scrna_seq", "visualization", "report"):
            assert stage in ALL_PIPELINE_STAGES

    def test_at_least_nine_stages(self) -> None:
        assert len(ALL_PIPELINE_STAGES) >= 9


class TestNextStage:
    def test_returns_first_uncompleted(self) -> None:
        assert _next_stage(_state(["qc", "alignment"], [])) == "qc"

    def test_skips_completed(self) -> None:
        assert _next_stage(_state(["qc", "alignment"], ["qc"])) == "alignment"

    def test_returns_end_when_all_done(self) -> None:
        assert _next_stage(_state(["qc", "alignment"], ["qc", "alignment"])) == END

    def test_returns_end_on_failure(self) -> None:
        assert _next_stage(_state(["qc", "alignment"], [], failed="qc")) == END

    def test_empty_stages_returns_end(self) -> None:
        assert _next_stage(_state([], [])) == END


class TestBuildPipelineGraph:
    @pytest.fixture
    def graph(self):
        return build_pipeline_graph()

    def test_compiles_without_error(self, graph) -> None:
        assert graph is not None

    def test_graph_has_stage_nodes(self, graph) -> None:
        nodes = set(graph.nodes)
        for stage in ALL_PIPELINE_STAGES:
            assert stage in nodes, f"Stage node '{stage}' missing from graph"

    def test_qc_alignment_both_complete(self, graph) -> None:
        result = graph.invoke(_state(["qc", "alignment"], []))
        assert "qc" in result["completed_stages"]
        assert "alignment" in result["completed_stages"]
        assert len(result["completed_stages"]) == 2

    def test_qc_only_does_not_enter_alignment(self, graph) -> None:
        result = graph.invoke(_state(["qc"], []))
        assert "qc" in result["completed_stages"]
        assert "alignment" not in result["completed_stages"]

    def test_three_stage_pipeline_completes_in_order(self, graph) -> None:
        result = graph.invoke(
            _state(["qc", "alignment", "quantification"], [])
        )
        assert result["completed_stages"] == ["qc", "alignment", "quantification"]

    def test_interrupted_graph_resumes_from_checkpoint(self, graph) -> None:
        # qc already done in checkpoint
        result = graph.invoke(_state(["qc", "alignment", "quantification"], ["qc"]))
        completed = result["completed_stages"]
        assert "qc" in completed
        assert "alignment" in completed
        assert "quantification" in completed

    def test_interrupted_skips_already_completed(self, graph) -> None:
        # Confirm qc was not re-executed (still appears exactly once)
        result = graph.invoke(_state(["qc", "alignment"], ["qc"]))
        assert result["completed_stages"].count("qc") == 1

    def test_failed_stage_stops_pipeline(self, graph) -> None:
        result = graph.invoke(_state(["qc", "alignment"], [], failed="qc"))
        assert "alignment" not in result["completed_stages"]

    def test_scrna_seq_completes_alone(self, graph) -> None:
        result = graph.invoke(_state(["scrna_seq"], []))
        assert "scrna_seq" in result["completed_stages"]

    def test_all_stages_can_be_executed(self, graph) -> None:
        result = graph.invoke(_state(ALL_PIPELINE_STAGES, []))
        assert set(result["completed_stages"]) == set(ALL_PIPELINE_STAGES)
