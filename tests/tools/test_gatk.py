"""Tests for run_gatk_haplotypecaller, run_gatk_variant_filter, and the VCF parser."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.base import ToolExecutionError, ToolTimeoutError
from src.tools.variant.gatk import (
    GATKHaplotypeCallerInput,
    GATKHaplotypeCallerOutput,
    GATKVariantFilterInput,
    GATKVariantFilterOutput,
    run_gatk_haplotypecaller,
    run_gatk_variant_filter,
)
from src.tools.variant.parsers import parse_vcf_variant_counts

FIXTURE_DIR = Path(__file__).parent / "fixtures"

VCF_TEXT = (FIXTURE_DIR / "sample.vcf").read_text()

# fixture: 5 variants total, 2 PASS, 3 filtered (QDFilter / FSFilter)
_VCF_COUNTS = {"total_count": 5, "pass_count": 2, "filtered_count": 3}


# ── VCF parser tests ───────────────────────────────────────────────────────────


class TestParseVcfVariantCounts:
    def test_total_count(self) -> None:
        result = parse_vcf_variant_counts(VCF_TEXT)
        assert result["total_count"] == 5

    def test_pass_count(self) -> None:
        result = parse_vcf_variant_counts(VCF_TEXT)
        assert result["pass_count"] == 2

    def test_filtered_count(self) -> None:
        result = parse_vcf_variant_counts(VCF_TEXT)
        assert result["filtered_count"] == 3

    def test_skips_header_lines(self) -> None:
        text = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        result = parse_vcf_variant_counts(text)
        assert result["total_count"] == 0

    def test_empty_text_returns_zeros(self) -> None:
        result = parse_vcf_variant_counts("")
        assert result["total_count"] == 0
        assert result["pass_count"] == 0
        assert result["filtered_count"] == 0

    def test_dot_filter_counts_as_pass(self) -> None:
        text = "chr1\t100\t.\tA\tT\t50\t.\t.\n"
        result = parse_vcf_variant_counts(text)
        assert result["pass_count"] == 1
        assert result["filtered_count"] == 0

    def test_compound_filter_counts_as_filtered(self) -> None:
        text = "chr1\t500\t.\tA\tG\t15\tQDFilter;FSFilter\t.\n"
        result = parse_vcf_variant_counts(text)
        assert result["filtered_count"] == 1
        assert result["pass_count"] == 0


# ── GATKHaplotypeCallerInput validation ────────────────────────────────────────


class TestGATKHaplotypeCallerInput:
    def _base(self, **kwargs) -> GATKHaplotypeCallerInput:  # type: ignore[no-untyped-def]
        return GATKHaplotypeCallerInput(
            bam_path="/data/ctrl.bam",
            bam_index_path="/data/ctrl.bam.bai",
            reference_fasta="/ref/GRCh38.fa",
            output_vcf_path="/out/ctrl.vcf",
            **kwargs,
        )

    def test_valid_defaults(self) -> None:
        inp = self._base()
        assert inp.dbsnp_path is None
        assert inp.interval_list is None
        assert inp.emit_ref_confidence == "NONE"
        assert inp.extra_args == []

    def test_dbsnp_optional(self) -> None:
        inp = self._base(dbsnp_path="/ref/dbsnp.vcf")
        assert inp.dbsnp_path == "/ref/dbsnp.vcf"

    def test_interval_list_optional(self) -> None:
        inp = self._base(interval_list="/ref/intervals.list")
        assert inp.interval_list == "/ref/intervals.list"

    def test_emit_ref_confidence_gvcf(self) -> None:
        inp = self._base(emit_ref_confidence="GVCF")
        assert inp.emit_ref_confidence == "GVCF"

    def test_invalid_emit_ref_confidence_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._base(emit_ref_confidence="INVALID")  # type: ignore[arg-type]


# ── run_gatk_haplotypecaller (subprocess mocked) ──────────────────────────────


class TestRunGATKHaplotypeCaller:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self, **kwargs) -> GATKHaplotypeCallerInput:  # type: ignore[no-untyped-def]
        return GATKHaplotypeCallerInput(
            bam_path="/data/ctrl.bam",
            bam_index_path="/data/ctrl.bam.bai",
            reference_fasta="/ref/GRCh38.fa",
            output_vcf_path="/out/ctrl.vcf",
            **kwargs,
        )

    @patch("src.tools.variant.gatk.detect_version", return_value="GATK 4.4.0.0")
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_success_returns_output(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_gatk_haplotypecaller(self._base_inp())
        assert isinstance(out, GATKHaplotypeCallerOutput)

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_variant_count_is_integer(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_gatk_haplotypecaller(self._base_inp())
        assert isinstance(out.variant_count, int)
        assert out.variant_count == 5

    @patch("src.tools.variant.gatk.detect_version", return_value="GATK 4.4.0.0")
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_tool_version_in_output(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_gatk_haplotypecaller(self._base_inp())
        assert out.tool_version == "GATK 4.4.0.0"

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_dbsnp_passed_when_provided(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_gatk_haplotypecaller(self._base_inp(dbsnp_path="/ref/dbsnp.vcf"))
        called_cmd = mock_run.call_args[0][0]
        assert "--dbsnp" in called_cmd
        assert "/ref/dbsnp.vcf" in called_cmd

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_dbsnp_omitted_when_none(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_gatk_haplotypecaller(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert "--dbsnp" not in called_cmd

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_interval_list_passed_when_provided(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_gatk_haplotypecaller(self._base_inp(interval_list="/ref/exome.list"))
        called_cmd = mock_run.call_args[0][0]
        assert "-L" in called_cmd
        assert "/ref/exome.list" in called_cmd

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_emit_ref_confidence_omitted_when_none(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_gatk_haplotypecaller(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert "--emit-ref-confidence" not in called_cmd

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_emit_ref_confidence_gvcf_in_command(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_gatk_haplotypecaller(self._base_inp(emit_ref_confidence="GVCF"))
        called_cmd = mock_run.call_args[0][0]
        assert "--emit-ref-confidence" in called_cmd
        assert "GVCF" in called_cmd

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_gatk_haplotypecaller(self._base_inp())
        assert exc_info.value.tool_name == "gatk"

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gatk"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_gatk_haplotypecaller(self._base_inp())


# ── GATKVariantFilterInput validation ─────────────────────────────────────────


class TestGATKVariantFilterInput:
    def _base(self) -> GATKVariantFilterInput:
        return GATKVariantFilterInput(
            vcf_path="/out/ctrl.vcf",
            reference_fasta="/ref/GRCh38.fa",
            output_vcf_path="/out/ctrl.filtered.vcf",
            snp_filter_expression="QD < 2.0 || FS > 60.0",
            indel_filter_expression="QD < 2.0 || FS > 200.0",
        )

    def test_valid_input(self) -> None:
        inp = self._base()
        assert "QD < 2.0" in inp.snp_filter_expression

    def test_filter_expressions_stored(self) -> None:
        inp = self._base()
        assert inp.snp_filter_expression == "QD < 2.0 || FS > 60.0"
        assert inp.indel_filter_expression == "QD < 2.0 || FS > 200.0"


# ── run_gatk_variant_filter (subprocess mocked) ────────────────────────────────


class TestRunGATKVariantFilter:
    def _mock_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = b""
        proc.stderr = b""
        return proc

    def _base_inp(self) -> GATKVariantFilterInput:
        return GATKVariantFilterInput(
            vcf_path="/out/ctrl.vcf",
            reference_fasta="/ref/GRCh38.fa",
            output_vcf_path="/out/ctrl.filtered.vcf",
            snp_filter_expression="QD < 2.0 || FS > 60.0",
            indel_filter_expression="QD < 2.0 || FS > 200.0",
        )

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_pass_and_filtered_counts(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_gatk_variant_filter(self._base_inp())
        assert isinstance(out, GATKVariantFilterOutput)
        assert out.pass_variant_count == 2
        assert out.filtered_variant_count == 3

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_filter_expressions_in_command(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        run_gatk_variant_filter(self._base_inp())
        called_cmd = mock_run.call_args[0][0]
        assert "--filter-expression" in called_cmd
        assert "QD < 2.0 || FS > 60.0" in called_cmd
        assert "QD < 2.0 || FS > 200.0" in called_cmd

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("src.tools.variant.gatk._count_vcf_variants", return_value=_VCF_COUNTS)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_output_vcf_path_correct(
        self, mock_run, mock_makedirs, mock_counts, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc()
        out = run_gatk_variant_filter(self._base_inp())
        assert out.filtered_vcf_path == "/out/ctrl.filtered.vcf"
        assert out.filtered_vcf_index_path == "/out/ctrl.filtered.vcf.tbi"

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_nonzero_exit_raises_tool_execution_error(
        self, mock_run, mock_makedirs, mock_version
    ) -> None:
        mock_run.return_value = self._mock_proc(returncode=1)
        with pytest.raises(ToolExecutionError) as exc_info:
            run_gatk_variant_filter(self._base_inp())
        assert exc_info.value.tool_name == "gatk"

    @patch("src.tools.variant.gatk.detect_version", return_value=None)
    @patch("os.makedirs")
    @patch("src.tools.base.subprocess.run")
    def test_timeout_raises_tool_timeout_error(self, mock_run, mock_makedirs, mock_version) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gatk"], timeout=3600)
        with pytest.raises(ToolTimeoutError):
            run_gatk_variant_filter(self._base_inp())
