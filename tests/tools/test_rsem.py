"""Tests for run_rsem."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.quantification.rsem import RSEMInput, RSEMOutput, run_rsem

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── RSEMInput validation ───────────────────────────────────────────────────────


class TestRSEMInput:
    def _base(self, **kwargs) -> RSEMInput:  # type: ignore[no-untyped-def]
        return RSEMInput(
            bam_path="/data/ctrl.transcriptome.bam",
            rsem_reference="/ref/rsem/GRCh38",
            output_prefix="/out/ctrl",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.paired_end is True
        assert inp.threads == 8
        assert inp.extra_args == []

    def test_paired_end_false(self) -> None:
        inp = self._base(paired_end=False)
        assert inp.paired_end is False

    def test_threads_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(threads=0)

    def test_threads_above_max_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(threads=257)

    def test_extra_args_stored(self) -> None:
        inp = self._base(extra_args=["--estimate-rspd"])
        assert inp.extra_args == ["--estimate-rspd"]


# ── run_rsem (subprocess mocked) ──────────────────────────────────────────────


class TestRunRSEM:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> RSEMInput:  # type: ignore[no-untyped-def]
        return RSEMInput(
            bam_path="/data/ctrl.transcriptome.bam",
            rsem_reference="/ref/rsem/GRCh38",
            output_prefix="/out/ctrl",
            **kwargs,
        )

    @patch("src.tools.quantification.rsem.detect_version", return_value="RSEM v1.3.3")
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_rsem_output(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rsem(self._base_inp())
        assert isinstance(out, RSEMOutput)

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_genes_results_path(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rsem(self._base_inp())
        assert out.genes_results_path == "/out/ctrl.genes.results"

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_isoforms_results_path(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rsem(self._base_inp())
        assert out.isoforms_results_path == "/out/ctrl.isoforms.results"

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_stat_dir_path(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rsem(self._base_inp())
        assert out.stat_dir == "/out/ctrl.stat"

    @patch("src.tools.quantification.rsem.detect_version", return_value="RSEM v1.3.3")
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_rsem(self._base_inp())
        assert out.tool_version == "RSEM v1.3.3"

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_paired_end_true_adds_flag(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        run_rsem(self._base_inp(paired_end=True))
        called_cmd = mock_run.call_args[0][0]
        assert "--paired-end" in called_cmd

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_paired_end_false_omits_flag(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        run_rsem(self._base_inp(paired_end=False))
        called_cmd = mock_run.call_args[0][0]
        assert "--paired-end" not in called_cmd

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_extra_args_in_command(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        run_rsem(self._base_inp(extra_args=["--estimate-rspd"]))
        called_cmd = mock_run.call_args[0][0]
        assert "--estimate-rspd" in called_cmd

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_positional_args_order(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        run_rsem(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        # bam_path, rsem_reference, output_prefix must be last three positional args
        assert called_cmd[-3] == "/data/ctrl.transcriptome.bam"
        assert called_cmd[-2] == "/ref/rsem/GRCh38"
        assert called_cmd[-1] == "/out/ctrl"

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_rsem(self._base_inp())
        assert exc_info.value.tool_name == "rsem-calculate-expression"

    @patch("src.tools.quantification.rsem.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["rsem-calculate-expression"], timeout=3600
        )
        with pytest.raises(ToolTimeoutError):
            run_rsem(self._base_inp())
