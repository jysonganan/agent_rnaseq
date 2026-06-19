"""Integration test: OrchestratorAgent.validate_stage_dependencies()."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import OrchestratorAgent, OrchestratorError


@pytest.fixture
def agent() -> OrchestratorAgent:
    return OrchestratorAgent(llm_client=MagicMock())


# ── Valid combinations ────────────────────────────────────────────────────────


def test_qc_only_is_valid(agent):
    agent.validate_stage_dependencies(["qc"])


def test_alignment_only_is_valid(agent):
    agent.validate_stage_dependencies(["alignment"])


def test_qc_and_alignment_is_valid(agent):
    agent.validate_stage_dependencies(["qc", "alignment"])


def test_alignment_quantification_is_valid(agent):
    agent.validate_stage_dependencies(["alignment", "quantification"])


def test_alignment_splicing_is_valid(agent):
    agent.validate_stage_dependencies(["alignment", "splicing"])


def test_alignment_variant_is_valid(agent):
    agent.validate_stage_dependencies(["alignment", "variant_calling"])


def test_full_bulk_pipeline_is_valid(agent):
    agent.validate_stage_dependencies(
        ["qc", "alignment", "quantification", "differential_expression", "gsea"]
    )


def test_de_with_quantification_and_alignment_is_valid(agent):
    agent.validate_stage_dependencies(["alignment", "quantification", "differential_expression"])


def test_gsea_with_full_chain_is_valid(agent):
    agent.validate_stage_dependencies(
        ["alignment", "quantification", "differential_expression", "gsea"]
    )


# ── Invalid combinations ──────────────────────────────────────────────────────


def test_quantification_without_alignment_raises(agent):
    with pytest.raises(OrchestratorError, match="alignment"):
        agent.validate_stage_dependencies(["quantification"])


def test_de_without_quantification_raises(agent):
    with pytest.raises(OrchestratorError):
        agent.validate_stage_dependencies(["alignment", "differential_expression"])


def test_de_without_alignment_raises(agent):
    with pytest.raises(OrchestratorError):
        agent.validate_stage_dependencies(["differential_expression"])


def test_gsea_without_de_raises(agent):
    with pytest.raises(OrchestratorError, match="differential_expression"):
        agent.validate_stage_dependencies(["alignment", "quantification", "gsea"])


def test_gsea_alone_raises(agent):
    with pytest.raises(OrchestratorError):
        agent.validate_stage_dependencies(["gsea"])


def test_splicing_without_alignment_raises(agent):
    with pytest.raises(OrchestratorError, match="alignment"):
        agent.validate_stage_dependencies(["splicing"])


def test_variant_calling_without_alignment_raises(agent):
    with pytest.raises(OrchestratorError, match="alignment"):
        agent.validate_stage_dependencies(["variant_calling"])


def test_visualization_without_any_results_stage_raises(agent):
    with pytest.raises(OrchestratorError):
        agent.validate_stage_dependencies(["visualization"])


def test_visualization_with_de_results_does_not_raise(agent):
    agent.validate_stage_dependencies(
        ["alignment", "quantification", "differential_expression", "visualization"]
    )
