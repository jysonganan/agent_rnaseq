"""Tests for RunState and StageState TypedDicts."""

from __future__ import annotations

from src.agents.state import RunState, StageState


class TestRunState:
    def test_creation_minimal(self) -> None:
        state = RunState(
            run_id="run-001",
            run_config={},
            stages=["qc"],
            completed_stages=[],
            failed_stage=None,
            stage_outputs={},
            error_message=None,
            current_stage=None,
        )
        assert state["run_id"] == "run-001"
        assert state["stages"] == ["qc"]

    def test_multiple_stages(self) -> None:
        state = RunState(
            run_id="r1",
            run_config={"alpha": 0.05},
            stages=["qc", "alignment", "quantification"],
            completed_stages=["qc"],
            failed_stage=None,
            stage_outputs={"qc": {"status": "pass"}},
            error_message=None,
            current_stage="alignment",
        )
        assert state["current_stage"] == "alignment"
        assert "qc" in state["completed_stages"]
        assert len(state["stages"]) == 3

    def test_failed_state(self) -> None:
        state = RunState(
            run_id="r1",
            run_config={},
            stages=["qc", "alignment"],
            completed_stages=["qc"],
            failed_stage="alignment",
            stage_outputs={},
            error_message="STAR exited with code 1",
            current_stage="alignment",
        )
        assert state["failed_stage"] == "alignment"
        assert state["error_message"] == "STAR exited with code 1"

    def test_stage_outputs_stored(self) -> None:
        outputs = {"qc": {"report": "/out/fastqc.html"}}
        state = RunState(
            run_id="r1",
            run_config={},
            stages=["qc"],
            completed_stages=["qc"],
            failed_stage=None,
            stage_outputs=outputs,
            error_message=None,
            current_stage="qc",
        )
        assert state["stage_outputs"]["qc"]["report"] == "/out/fastqc.html"


class TestStageState:
    def test_completed_stage(self) -> None:
        s = StageState(
            stage_name="qc",
            status="completed",
            output={"report": "/out/fastqc.html"},
            error=None,
        )
        assert s["stage_name"] == "qc"
        assert s["status"] == "completed"
        assert s["error"] is None

    def test_failed_stage(self) -> None:
        s = StageState(
            stage_name="alignment",
            status="failed",
            output=None,
            error="STAR failed with exit code 1",
        )
        assert s["status"] == "failed"
        assert s["output"] is None
        assert "STAR" in s["error"]

    def test_running_stage(self) -> None:
        s = StageState(
            stage_name="quantification",
            status="running",
            output=None,
            error=None,
        )
        assert s["status"] == "running"
