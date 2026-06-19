"""Tests for NextflowRunner and config_builder."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.tools.base import ExecutionBackend
from src.tools.nextflow.config_builder import build_config_overrides, build_params
from src.tools.nextflow.runner import NextflowRunConfig, NextflowRunner, NextflowStatus


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_proc(poll_return: int | None) -> MagicMock:
    proc = MagicMock()
    proc.poll.return_value = poll_return
    return proc


def _submit(runner: NextflowRunner, workflow: str = "nextflow/main.nf") -> str:
    config = NextflowRunConfig(workflow_path=workflow, profile="local")
    return runner.submit(config)


# ── NextflowRunner.submit ─────────────────────────────────────────────────────


class TestNextflowRunnerSubmit:
    def test_calls_popen(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            _submit(runner)
            mock_popen.assert_called_once()

    def test_cmd_starts_with_nextflow_run(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            _submit(runner)
            cmd = mock_popen.call_args[0][0]
            assert cmd[0] == "nextflow"
            assert "run" in cmd

    def test_cmd_includes_workflow_path(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            _submit(runner, "nextflow/main.nf")
            cmd = mock_popen.call_args[0][0]
            assert "nextflow/main.nf" in cmd

    def test_cmd_includes_profile(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            config = NextflowRunConfig(workflow_path="nf/main.nf", profile="awsbatch")
            runner.submit(config)
            cmd = mock_popen.call_args[0][0]
            assert "-profile" in cmd
            assert "awsbatch" in cmd

    def test_returns_valid_uuid(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)):
            runner = NextflowRunner()
            run_id = _submit(runner)
            uuid.UUID(run_id)  # raises ValueError if not a valid UUID

    def test_params_included_as_flags(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            config = NextflowRunConfig(
                workflow_path="nf/main.nf",
                params={"output_dir": "/out", "genome_dir": "/ref/hg38"},
            )
            runner.submit(config)
            cmd = mock_popen.call_args[0][0]
            assert "--output_dir" in cmd
            assert "/out" in cmd
            assert "--genome_dir" in cmd
            assert "/ref/hg38" in cmd

    def test_work_dir_flag_included_when_set(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            config = NextflowRunConfig(workflow_path="nf/main.nf", work_dir="/tmp/nf")
            runner.submit(config)
            cmd = mock_popen.call_args[0][0]
            assert "-work-dir" in cmd
            assert "/tmp/nf" in cmd

    def test_work_dir_absent_when_not_set(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            config = NextflowRunConfig(workflow_path="nf/main.nf")
            runner.submit(config)
            cmd = mock_popen.call_args[0][0]
            assert "-work-dir" not in cmd

    def test_extra_args_appended(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner()
            config = NextflowRunConfig(
                workflow_path="nf/main.nf", extra_args=["-resume", "-with-trace"]
            )
            runner.submit(config)
            cmd = mock_popen.call_args[0][0]
            assert "-resume" in cmd
            assert "-with-trace" in cmd

    def test_custom_nextflow_bin(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)) as mock_popen:
            runner = NextflowRunner(nextflow_bin="/usr/local/bin/nextflow")
            _submit(runner)
            cmd = mock_popen.call_args[0][0]
            assert cmd[0] == "/usr/local/bin/nextflow"


# ── NextflowRunner.poll ───────────────────────────────────────────────────────


class TestNextflowRunnerPoll:
    def test_running_when_process_active(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(None)):
            runner = NextflowRunner()
            run_id = _submit(runner)
            assert runner.poll(run_id) == NextflowStatus.running

    def test_completed_when_exit_zero(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(0)):
            runner = NextflowRunner()
            run_id = _submit(runner)
            assert runner.poll(run_id) == NextflowStatus.completed

    def test_failed_when_nonzero_exit(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(1)):
            runner = NextflowRunner()
            run_id = _submit(runner)
            assert runner.poll(run_id) == NextflowStatus.failed

    def test_unknown_for_untracked_run_id(self) -> None:
        runner = NextflowRunner()
        assert runner.poll("no-such-id") == NextflowStatus.unknown

    def test_failed_exit_code_2(self) -> None:
        with patch("subprocess.Popen", return_value=_mock_proc(2)):
            runner = NextflowRunner()
            run_id = _submit(runner)
            assert runner.poll(run_id) == NextflowStatus.failed


# ── NextflowRunner.cancel ─────────────────────────────────────────────────────


class TestNextflowRunnerCancel:
    def test_calls_terminate_on_running_process(self) -> None:
        proc = _mock_proc(None)
        with patch("subprocess.Popen", return_value=proc):
            runner = NextflowRunner()
            run_id = _submit(runner)
            runner.cancel(run_id)
            proc.terminate.assert_called_once()

    def test_cancel_noop_for_unknown_id(self) -> None:
        runner = NextflowRunner()
        runner.cancel("no-such-id")  # must not raise


# ── ExecutionBackend enum ─────────────────────────────────────────────────────


class TestExecutionBackend:
    def test_local_value(self) -> None:
        assert ExecutionBackend.local == "local"

    def test_nextflow_value(self) -> None:
        assert ExecutionBackend.nextflow == "nextflow"

    def test_aws_batch_value(self) -> None:
        assert ExecutionBackend.aws_batch == "aws_batch"


# ── config_builder ────────────────────────────────────────────────────────────


class TestBuildConfigOverrides:
    def test_local_executor_in_output(self) -> None:
        out = build_config_overrides({"executor": "local", "cpus": 4, "memory_gb": 16})
        assert "local" in out

    def test_local_cpus_in_output(self) -> None:
        out = build_config_overrides({"executor": "local", "cpus": 8, "memory_gb": 32})
        assert "8" in out

    def test_local_memory_in_output(self) -> None:
        out = build_config_overrides({"executor": "local", "cpus": 4, "memory_gb": 32})
        assert "32 GB" in out

    def test_awsbatch_executor_in_output(self) -> None:
        out = build_config_overrides({"executor": "aws_batch", "cpus": 16, "memory_gb": 64})
        assert "awsbatch" in out

    def test_awsbatch_cpus_in_output(self) -> None:
        out = build_config_overrides({"executor": "aws_batch", "cpus": 16, "memory_gb": 64})
        assert "16" in out

    def test_awsbatch_memory_in_output(self) -> None:
        out = build_config_overrides({"executor": "aws_batch", "cpus": 4, "memory_gb": 64})
        assert "64 GB" in out

    def test_awsbatch_includes_queue(self) -> None:
        out = build_config_overrides(
            {"executor": "aws_batch", "cpus": 4, "memory_gb": 16, "aws_batch_queue": "my-queue"}
        )
        assert "my-queue" in out

    def test_awsbatch_includes_s3_work_dir(self) -> None:
        out = build_config_overrides(
            {"executor": "aws_batch", "cpus": 4, "memory_gb": 16, "s3_work_dir": "s3://my-bucket/work/"}
        )
        assert "s3://my-bucket/work/" in out

    def test_awsbatch_includes_region(self) -> None:
        out = build_config_overrides(
            {"executor": "aws_batch", "cpus": 4, "memory_gb": 16, "aws_region": "eu-west-1"}
        )
        assert "eu-west-1" in out

    def test_default_executor_is_local(self) -> None:
        out = build_config_overrides({"cpus": 4, "memory_gb": 8})
        assert "local" in out

    def test_local_sets_work_dir(self) -> None:
        out = build_config_overrides({"executor": "local", "cpus": 4, "memory_gb": 8})
        assert "workDir" in out


class TestBuildParams:
    def test_output_dir_always_included(self) -> None:
        p = build_params(output_dir="/results")
        assert p["output_dir"] == "/results"

    def test_none_values_excluded(self) -> None:
        p = build_params(output_dir="/results", genome_dir=None, fastq_r2=None)
        assert "genome_dir" not in p
        assert "fastq_r2" not in p

    def test_non_none_values_included(self) -> None:
        p = build_params(output_dir="/out", genome_dir="/ref/hg38", fastq_r1="/data/r1.fq.gz")
        assert p["genome_dir"] == "/ref/hg38"
        assert p["fastq_r1"] == "/data/r1.fq.gz"

    def test_extra_kwargs_merged(self) -> None:
        p = build_params(output_dir="/out", threads=16)
        assert p["threads"] == 16
