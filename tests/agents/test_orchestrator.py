"""Tests for OrchestratorAgent, RunConfig, and BaseStageAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.agents.base_agent import BaseStageAgent, MockToolRegistry
from src.agents.orchestrator import OrchestratorAgent, OrchestratorError, RunConfig
from src.agents.state import RunState
from src.db.enums import Executor, PipelineType, StageName

_GENOMES = [
    {"id": "g1", "name": "GRCh38", "species": "human"},
    {"id": "g2", "name": "GRCm39", "species": "mouse"},
]


def _make_agent(dry_run: bool = False) -> OrchestratorAgent:
    return OrchestratorAgent(llm_client=MagicMock(), dry_run=dry_run)


# ── RunConfig validation ───────────────────────────────────────────────────────


class TestRunConfig:
    def test_valid_defaults(self) -> None:
        cfg = RunConfig(run_name="r1", genome_id="g1", stages=[StageName.qc])
        assert cfg.alpha == pytest.approx(0.05)
        assert cfg.lfc_threshold == pytest.approx(0.0)
        assert cfg.executor == Executor.local
        assert cfg.dry_run is False
        assert cfg.pipeline_type == PipelineType.bulk_rnaseq

    def test_alpha_below_min_raises(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(run_name="r", genome_id="g1", stages=[StageName.qc], alpha=0.0009)

    def test_alpha_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(run_name="r", genome_id="g1", stages=[StageName.qc], alpha=0.11)

    def test_alpha_at_bounds_ok(self) -> None:
        cfg = RunConfig(run_name="r", genome_id="g1", stages=[StageName.qc], alpha=0.001)
        assert cfg.alpha == pytest.approx(0.001)
        cfg2 = RunConfig(run_name="r", genome_id="g1", stages=[StageName.qc], alpha=0.1)
        assert cfg2.alpha == pytest.approx(0.1)

    def test_empty_stages_raises(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(run_name="r", genome_id="g1", stages=[])

    def test_lfc_threshold_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(
                run_name="r",
                genome_id="g1",
                stages=[StageName.qc],
                lfc_threshold=-0.1,
            )

    def test_lfc_threshold_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(
                run_name="r",
                genome_id="g1",
                stages=[StageName.qc],
                lfc_threshold=5.1,
            )

    def test_dry_run_false_by_default(self) -> None:
        cfg = RunConfig(run_name="r", genome_id="g1", stages=[StageName.qc])
        assert cfg.dry_run is False

    def test_dry_run_settable_directly(self) -> None:
        cfg = RunConfig(run_name="r", genome_id="g1", stages=[StageName.qc], dry_run=True)
        assert cfg.dry_run is True


# ── validate_stage_dependencies ───────────────────────────────────────────────


class TestValidateStageDependencies:
    def test_valid_full_pipeline(self) -> None:
        _make_agent().validate_stage_dependencies(
            ["qc", "alignment", "quantification", "differential_expression", "gsea"]
        )

    def test_de_without_quantification_raises(self) -> None:
        with pytest.raises(OrchestratorError, match="quantification"):
            _make_agent().validate_stage_dependencies(["differential_expression"])

    def test_quantification_without_alignment_raises(self) -> None:
        with pytest.raises(OrchestratorError, match="alignment"):
            _make_agent().validate_stage_dependencies(["quantification"])

    def test_gsea_requires_de(self) -> None:
        with pytest.raises(OrchestratorError, match="differential_expression"):
            _make_agent().validate_stage_dependencies(["gsea"])

    def test_splicing_requires_alignment(self) -> None:
        with pytest.raises(OrchestratorError, match="alignment"):
            _make_agent().validate_stage_dependencies(["splicing"])

    def test_variant_calling_requires_alignment(self) -> None:
        with pytest.raises(OrchestratorError, match="alignment"):
            _make_agent().validate_stage_dependencies(["variant_calling"])

    def test_visualization_without_upstream_raises(self) -> None:
        with pytest.raises(OrchestratorError, match="visualization"):
            _make_agent().validate_stage_dependencies(["visualization"])

    def test_visualization_with_qc_ok(self) -> None:
        _make_agent().validate_stage_dependencies(["qc", "visualization"])

    def test_visualization_with_de_ok(self) -> None:
        _make_agent().validate_stage_dependencies(
            ["alignment", "quantification", "differential_expression", "visualization"]
        )

    def test_scrna_seq_no_deps(self) -> None:
        _make_agent().validate_stage_dependencies(["scrna_seq"])

    def test_qc_alone_ok(self) -> None:
        _make_agent().validate_stage_dependencies(["qc"])

    def test_report_alone_ok(self) -> None:
        _make_agent().validate_stage_dependencies(["report"])


# ── validate_genome ────────────────────────────────────────────────────────────


class TestValidateGenome:
    def test_valid_genome_ok(self) -> None:
        _make_agent().validate_genome("g1", _GENOMES)

    def test_second_genome_ok(self) -> None:
        _make_agent().validate_genome("g2", _GENOMES)

    def test_unknown_genome_raises(self) -> None:
        with pytest.raises(OrchestratorError, match="not found"):
            _make_agent().validate_genome("g99", _GENOMES)

    def test_empty_genome_list_raises(self) -> None:
        with pytest.raises(OrchestratorError):
            _make_agent().validate_genome("g1", [])


# ── parse_intent ──────────────────────────────────────────────────────────────


class TestParseIntent:
    def _mock_response(self, payload: dict) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps(payload)
        return mock_resp

    def test_returns_parsed_dict(self) -> None:
        agent = _make_agent()
        agent._client.chat.completions.create.return_value = self._mock_response(
            {
                "run_name": "my_run",
                "genome_id": "g1",
                "pipeline_type": "bulk_rnaseq",
                "stages": ["qc", "alignment"],
                "alpha": 0.05,
                "lfc_threshold": 0.0,
            }
        )
        with patch("src.agents.orchestrator.get_settings") as mock_cfg:
            mock_cfg.return_value.agent_llm_model = "gpt-4o"
            result = agent.parse_intent("Run bulk RNA-seq with GRCh38", _GENOMES)
        assert result["run_name"] == "my_run"
        assert "alignment" in result["stages"]

    def test_no_real_api_call(self) -> None:
        agent = _make_agent()
        agent._client.chat.completions.create.return_value = self._mock_response(
            {
                "run_name": "r",
                "genome_id": "g1",
                "pipeline_type": "bulk_rnaseq",
                "stages": ["qc"],
                "alpha": 0.05,
                "lfc_threshold": 0.0,
            }
        )
        with patch("src.agents.orchestrator.get_settings") as mock_cfg:
            mock_cfg.return_value.agent_llm_model = "gpt-4o"
            agent.parse_intent("Run QC only", _GENOMES)
        agent._client.chat.completions.create.assert_called_once()

    def test_genome_list_included_in_prompt(self) -> None:
        agent = _make_agent()
        agent._client.chat.completions.create.return_value = self._mock_response(
            {
                "run_name": "r",
                "genome_id": "g1",
                "pipeline_type": "bulk_rnaseq",
                "stages": ["qc"],
                "alpha": 0.05,
                "lfc_threshold": 0.0,
            }
        )
        with patch("src.agents.orchestrator.get_settings") as mock_cfg:
            mock_cfg.return_value.agent_llm_model = "gpt-4o"
            agent.parse_intent("Run QC", _GENOMES)
        call_kwargs = agent._client.chat.completions.create.call_args
        messages = call_kwargs[1]["messages"]
        system_content = messages[0]["content"]
        assert "GRCh38" in system_content
        assert "GRCm39" in system_content


# ── dispatch & resume ──────────────────────────────────────────────────────────


class TestDispatch:
    def test_qc_only_completes(self) -> None:
        cfg = RunConfig(run_name="r1", genome_id="g1", stages=[StageName.qc])
        result = _make_agent().dispatch(cfg, run_id="run-001")
        assert "qc" in result["completed_stages"]

    def test_qc_alignment_both_complete(self) -> None:
        cfg = RunConfig(
            run_name="r1",
            genome_id="g1",
            stages=[StageName.qc, StageName.alignment],
        )
        result = _make_agent().dispatch(cfg, run_id="run-002")
        assert "qc" in result["completed_stages"]
        assert "alignment" in result["completed_stages"]

    def test_run_id_preserved_in_state(self) -> None:
        cfg = RunConfig(run_name="r1", genome_id="g1", stages=[StageName.qc])
        result = _make_agent().dispatch(cfg, run_id="run-xyz")
        assert result["run_id"] == "run-xyz"

    def test_stages_serialised_from_enum(self) -> None:
        cfg = RunConfig(
            run_name="r1",
            genome_id="g1",
            stages=[StageName.qc, StageName.alignment],
        )
        result = _make_agent().dispatch(cfg, run_id="run-003")
        assert result["stages"] == ["qc", "alignment"]


class TestResume:
    def test_resumes_from_checkpoint_with_qc_done(self) -> None:
        checkpoint: RunState = {
            "run_id": "run-cp",
            "run_config": {},
            "stages": ["qc", "alignment"],
            "completed_stages": ["qc"],
            "failed_stage": None,
            "stage_outputs": {},
            "error_message": None,
            "current_stage": "qc",
        }
        result = _make_agent().resume(checkpoint)
        assert "alignment" in result["completed_stages"]

    def test_resume_does_not_duplicate_completed(self) -> None:
        checkpoint: RunState = {
            "run_id": "run-cp2",
            "run_config": {},
            "stages": ["qc", "alignment"],
            "completed_stages": ["qc"],
            "failed_stage": None,
            "stage_outputs": {},
            "error_message": None,
            "current_stage": "qc",
        }
        result = _make_agent().resume(checkpoint)
        assert result["completed_stages"].count("qc") == 1


# ── AGENT_LLM_MODEL config validation ─────────────────────────────────────────


class TestAgentLLMModelConfig:
    def test_valid_model_gpt4o(self) -> None:
        from src.config import Settings

        s = Settings(
            openai_api_key="sk-test",
            api_key_bootstrap="test",
            agent_llm_model="gpt-4o",
        )
        assert s.agent_llm_model == "gpt-4o"

    def test_valid_model_gpt4o_mini(self) -> None:
        from src.config import Settings

        s = Settings(
            openai_api_key="sk-test",
            api_key_bootstrap="test",
            agent_llm_model="gpt-4o-mini",
        )
        assert s.agent_llm_model == "gpt-4o-mini"

    def test_invalid_model_raises_validation_error(self) -> None:
        from src.config import Settings

        with pytest.raises((ValidationError, Exception)):
            Settings(
                openai_api_key="sk-test",
                api_key_bootstrap="test",
                agent_llm_model="gpt-3.5-turbo",
            )

    def test_default_model_is_gpt4o(self) -> None:
        from src.config import Settings

        s = Settings(openai_api_key="sk-test", api_key_bootstrap="test")
        assert s.agent_llm_model == "gpt-4o"


# ── BaseStageAgent ────────────────────────────────────────────────────────────


def _run_state() -> RunState:
    return RunState(
        run_id="r1",
        run_config={},
        stages=["qc"],
        completed_stages=[],
        failed_stage=None,
        stage_outputs={},
        error_message=None,
        current_stage=None,
    )


class ConcreteStage(BaseStageAgent):
    def __init__(self, stage_name: str, return_val: dict, **kwargs) -> None:
        super().__init__(stage_name, **kwargs)
        self._return_val = return_val

    def _run(self, state: RunState) -> dict:
        return self._return_val


class BrokenStage(BaseStageAgent):
    def _run(self, state: RunState) -> dict:
        raise RuntimeError("Tool subprocess failed")


class TestBaseStageAgent:
    def test_live_run_completed(self) -> None:
        agent = ConcreteStage("qc", {"report": "/out/fastqc.html"})
        result = agent.execute(_run_state())
        assert result["status"] == "completed"
        assert result["output"] == {"report": "/out/fastqc.html"}
        assert result["error"] is None

    def test_failed_run_captured(self) -> None:
        agent = BrokenStage("alignment", dry_run=False)
        result = agent.execute(_run_state())
        assert result["status"] == "failed"
        assert result["output"] is None
        assert "Tool subprocess failed" in result["error"]

    def test_dry_run_returns_mock_fixture(self) -> None:
        registry = MockToolRegistry()
        registry.register("qc", {"mock": "fastqc_report.html"})
        agent = BrokenStage("qc", dry_run=True, mock_registry=registry)
        result = agent.execute(_run_state())
        assert result["status"] == "completed"
        assert result["output"] == {"mock": "fastqc_report.html"}

    def test_dry_run_never_calls_run(self) -> None:
        class ShouldNotRun(BaseStageAgent):
            def _run(self, state: RunState) -> dict:
                raise AssertionError("_run called in dry_run mode")

        agent = ShouldNotRun("qc", dry_run=True)
        result = agent.execute(_run_state())
        assert result["status"] == "completed"

    def test_dry_run_empty_output_when_no_fixture(self) -> None:
        agent = BrokenStage("alignment", dry_run=True)
        result = agent.execute(_run_state())
        assert result["status"] == "completed"
        assert result["output"] == {}


class TestMockToolRegistry:
    def test_register_and_retrieve(self) -> None:
        registry = MockToolRegistry()
        registry.register("qc", {"report": "/mock.html"})
        assert registry.get_mock_output("qc") == {"report": "/mock.html"}

    def test_missing_key_returns_empty_dict(self) -> None:
        registry = MockToolRegistry()
        assert registry.get_mock_output("alignment") == {}

    def test_overwrite_fixture(self) -> None:
        registry = MockToolRegistry()
        registry.register("qc", {"v": 1})
        registry.register("qc", {"v": 2})
        assert registry.get_mock_output("qc") == {"v": 2}
