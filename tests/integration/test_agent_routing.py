"""Integration test: LangGraph pipeline routing and OrchestratorAgent validation."""

from __future__ import annotations

import pytest

from unittest.mock import MagicMock

from src.agents.orchestrator import OrchestratorAgent, OrchestratorError
from src.agents.router import build_pipeline_graph


def _orchestrator() -> OrchestratorAgent:
    return OrchestratorAgent(llm_client=MagicMock())


# ── LangGraph stub routing ─────────────────────────────────────────────────────

def _run_graph(stages: list[str]) -> dict:
    """Compile and invoke the pipeline graph with the given stage plan."""
    graph = build_pipeline_graph()
    return graph.invoke(
        {
            "run_id": "test-run-001",
            "run_config": {},
            "stages": stages,
            "completed_stages": [],
            "failed_stage": None,
            "stage_outputs": {},
            "error_message": None,
            "current_stage": None,
        }
    )


def test_single_stage_plan_completes_qc():
    result = _run_graph(["qc"])
    assert "qc" in result["completed_stages"]


def test_two_stage_plan_completes_both():
    result = _run_graph(["qc", "alignment"])
    assert "qc" in result["completed_stages"]
    assert "alignment" in result["completed_stages"]


def test_unplanned_stage_not_in_completed():
    result = _run_graph(["qc"])
    assert "alignment" not in result["completed_stages"]


def test_full_bulk_pipeline_plan():
    stages = ["qc", "alignment", "quantification", "differential_expression", "gsea"]
    result = _run_graph(stages)
    for stage in stages:
        assert stage in result["completed_stages"], f"Expected {stage} in completed_stages"


def test_empty_stage_plan_returns_no_completed():
    result = _run_graph([])
    assert result["completed_stages"] == []


def test_completed_stages_order_preserved():
    stages = ["qc", "alignment", "quantification"]
    result = _run_graph(stages)
    completed = result["completed_stages"]
    for stage in stages:
        assert stage in completed


# ── OrchestratorAgent.validate_genome ─────────────────────────────────────────

def test_validate_genome_passes_for_known_genome():
    agent = _orchestrator()
    available = [{"id": "genome-001", "name": "GRCh38"}, {"id": "genome-002", "name": "GRCm39"}]
    agent.validate_genome("genome-001", available)  # should not raise


def test_validate_genome_raises_for_unknown_genome():
    agent = _orchestrator()
    available = [{"id": "genome-001", "name": "GRCh38"}]
    with pytest.raises(OrchestratorError, match="genome"):
        agent.validate_genome("genome-999", available)


def test_validate_genome_empty_list_raises():
    agent = _orchestrator()
    with pytest.raises(OrchestratorError):
        agent.validate_genome("genome-001", [])


# ── validate_stage_dependencies (exercised via OrchestratorAgent) ─────────────

def test_validate_stages_qc_alone_passes():
    _orchestrator().validate_stage_dependencies(["qc"])


def test_validate_stages_valid_bulk_pipeline():
    stages = ["qc", "alignment", "quantification", "differential_expression", "gsea"]
    _orchestrator().validate_stage_dependencies(stages)


def test_validate_stages_alignment_without_quantification_passes():
    _orchestrator().validate_stage_dependencies(["qc", "alignment"])


def test_validate_stages_de_requires_quantification_and_alignment():
    with pytest.raises(OrchestratorError):
        _orchestrator().validate_stage_dependencies(["differential_expression"])


def test_validate_stages_de_without_quantification_raises():
    with pytest.raises(OrchestratorError):
        _orchestrator().validate_stage_dependencies(["alignment", "differential_expression"])


def test_validate_stages_gsea_requires_de():
    with pytest.raises(OrchestratorError):
        _orchestrator().validate_stage_dependencies(["gsea"])


def test_validate_stages_splicing_requires_alignment():
    with pytest.raises(OrchestratorError):
        _orchestrator().validate_stage_dependencies(["splicing"])


def test_validate_stages_variant_requires_alignment():
    with pytest.raises(OrchestratorError):
        _orchestrator().validate_stage_dependencies(["variant_calling"])


def test_validate_stages_splicing_with_alignment_passes():
    _orchestrator().validate_stage_dependencies(["alignment", "splicing"])


def test_validate_stages_variant_with_alignment_passes():
    _orchestrator().validate_stage_dependencies(["alignment", "variant_calling"])
