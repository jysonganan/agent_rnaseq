"""Tests for run_salmon_quant and the Salmon meta_info parser."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.quantification.parsers import parse_salmon_meta_info
from src.tools.quantification.salmon import SalmonQuantInput, SalmonQuantOutput, run_salmon_quant

FIXTURE_DIR = Path(__file__).parent / "fixtures"

META_INFO_TEXT = (FIXTURE_DIR / "salmon_meta_info.json").read_text()
META_INFO_DICT = json.loads(META_INFO_TEXT)


# ── Parser tests ───────────────────────────────────────────────────────────────


class TestParseSalmonMetaInfo:
    def test_mapping_rate(self) -> None:
        result = parse_salmon_meta_info(META_INFO_DICT)
        assert result["mapping_rate"] == pytest.approx(95.0)

    def test_inferred_lib_type(self) -> None:
        result = parse_salmon_meta_info(META_INFO_DICT)
        assert result["inferred_lib_type"] == "ISR"

    def test_fallback_to_library_types_list(self) -> None:
        data = {"library_types": ["ISF"], "mappingRate": 90.0}
        result = parse_salmon_meta_info(data)
        assert result["inferred_lib_type"] == "ISF"

    def test_fallback_percent_mapped_key(self) -> None:
        data = {"percent_mapped": 88.5, "inferred_library_type": "U"}
        result = parse_salmon_meta_info(data)
        assert result["mapping_rate"] == pytest.approx(88.5)

    def test_empty_dict_returns_defaults(self) -> None:
        result = parse_salmon_meta_info({})
        assert result["mapping_rate"] == 0.0
        assert result["inferred_lib_type"] == "unknown"

    def test_mapping_rate_is_float(self) -> None:
        result = parse_salmon_meta_info({"mappingRate": 95})
        assert isinstance(result["mapping_rate"], float)


# ── SalmonQuantInput validation ────────────────────────────────────────────────


class TestSalmonQuantInput:
    def _base(self, **kwargs) -> SalmonQuantInput:  # type: ignore[no-untyped-def]
        return SalmonQuantInput(
            fastq_r1="/data/ctrl_R1.fastq.gz",
            index_path="/ref/salmon_index",
            output_dir="/out/ctrl_quant",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.lib_type == "A"
        assert inp.threads == 8
        assert inp.fastq_r2 is None
        assert inp.extra_args == []

    def test_paired_end_r2(self) -> None:
        inp = self._base(fastq_r2="/data/ctrl_R2.fastq.gz")
        assert inp.fastq_r2 == "/data/ctrl_R2.fastq.gz"

    def test_threads_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(threads=0)

    def test_custom_lib_type(self) -> None:
        inp = self._base(lib_type="ISR")
        assert inp.lib_type == "ISR"

    def test_extra_args_stored(self) -> None:
        inp = self._base(extra_args=["--gcBias"])
        assert inp.extra_args == ["--gcBias"]


# ── run_salmon_quant (subprocess mocked) ──────────────────────────────────────


class TestRunSalmonQuant:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> SalmonQuantInput:  # type: ignore[no-untyped-def]
        return SalmonQuantInput(
            fastq_r1="/data/ctrl_R1.fastq.gz",
            index_path="/ref/salmon_index",
            output_dir="/out/ctrl_quant",
            **kwargs,
        )

    @patch("src.tools.quantification.salmon.detect_version", return_value="salmon 1.10.0")
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_single_end(self, mock_run, mock_makedirs, mock_exists, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            out = run_salmon_quant(self._base_inp())
        assert isinstance(out, SalmonQuantOutput)
        assert out.mapping_rate == pytest.approx(95.0)
        assert out.inferred_lib_type == "ISR"

    @patch("src.tools.quantification.salmon.detect_version", return_value="salmon 1.10.0")
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_single_end_uses_r_flag(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            run_salmon_quant(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert "-r" in called_cmd
        assert "-1" not in called_cmd

    @patch("src.tools.quantification.salmon.detect_version", return_value=None)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_paired_end_uses_1_2_flags(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            run_salmon_quant(self._base_inp(fastq_r2="/data/ctrl_R2.fastq.gz"))
        called_cmd = mock_run.call_args[0][0]
        assert "-1" in called_cmd
        assert "-2" in called_cmd
        assert "-r" not in called_cmd

    @patch("src.tools.quantification.salmon.detect_version", return_value="salmon 1.10.0")
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            out = run_salmon_quant(self._base_inp())
        assert out.tool_version == "salmon 1.10.0"

    @patch("src.tools.quantification.salmon.detect_version", return_value=None)
    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_eq_classes_path_present_when_file_exists(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            out = run_salmon_quant(self._base_inp())
        assert out.eq_classes_path is not None
        assert "eq_classes" in out.eq_classes_path

    @patch("src.tools.quantification.salmon.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_salmon_quant(self._base_inp())
        assert exc_info.value.tool_name == "salmon"

    @patch("src.tools.quantification.salmon.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["salmon"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_salmon_quant(self._base_inp())

    @patch("src.tools.quantification.salmon.detect_version", return_value=None)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_extra_args_in_command(
        self, mock_run, mock_makedirs, mock_exists, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            run_salmon_quant(self._base_inp(extra_args=["--gcBias"]))
        called_cmd = mock_run.call_args[0][0]
        assert "--gcBias" in called_cmd

    @patch("src.tools.quantification.salmon.detect_version", return_value=None)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_output_paths_correct(self, mock_run, mock_makedirs, mock_exists, mock_version) -> None:
        mock_run.return_value = self._mock_proc()
        with (
            patch("builtins.open", mock_open(read_data=META_INFO_TEXT)),
            patch("json.load", return_value=META_INFO_DICT),
        ):
            out = run_salmon_quant(self._base_inp())
        assert out.quant_sf_path.endswith("quant.sf")
        assert out.meta_info_path.endswith("meta_info.json")
        assert out.lib_format_counts_path.endswith("lib_format_counts.json")
