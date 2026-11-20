"""Nextflow compute backend for heavy per-sample stages (executor = nextflow | aws_batch).

``NextflowStageRunner.compute_for(stage)`` returns a function with the same contract as a
specialist's ``compute(stage_input)``: it runs ``nextflow/main.nf`` for one stage and one
sample (``-profile local`` or ``awsbatch``), then builds the **same validated ToolOutput
models** the local tools return, from the files Nextflow published to ``--output_dir``.
The specialist's ``persist`` step (DB rows, artifacts) is unchanged.

Only small files are read by the worker (logs, counts, FastQC zips, VCFs); BAMs stay where
Nextflow published them (local dir or S3) and are referenced by path.
"""

from __future__ import annotations

import json
import os
import posixpath
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.tools.alignment.parsers import parse_star_log_final
from src.tools.alignment.samtools import SamtoolsOutput
from src.tools.alignment.star import STARAlignOutput
from src.tools.base import ToolExecutionError, ToolValidationError
from src.tools.nextflow.config_builder import build_config_overrides
from src.tools.nextflow.storage import LocalStorage, Storage
from src.tools.qc.fastqc import FastQCOutput, _read_zip_summary, _sample_stem
from src.tools.quantification.htseq import HTSeqOutput
from src.tools.quantification.parsers import parse_htseq_counts, parse_salmon_meta_info
from src.tools.quantification.rsem import RSEMOutput
from src.tools.quantification.salmon import SalmonQuantOutput
from src.tools.variant.gatk import (
    GATKHaplotypeCallerOutput,
    GATKVariantFilterOutput,
    _count_vcf_variants,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
MAIN_NF = str(_REPO_ROOT / "nextflow" / "main.nf")
TOOL_VERSIONS_FILE = _REPO_ROOT / "docker" / "tool_versions.txt"

NEXTFLOW_STAGES: frozenset[str] = frozenset(
    {"qc", "alignment", "quantification", "variant_calling"}
)


class NextflowCancelledError(Exception):
    """The run was cancelled while Nextflow was running; the process was terminated."""


def pinned_version(tool: str) -> str | None:
    """Version of ``tool`` in the tools image, from docker/tool_versions.txt (≤32 chars)."""
    try:
        for line in TOOL_VERSIONS_FILE.read_text().splitlines():
            name, _, version = line.partition("=")
            if name.strip().lower() == tool.lower() and version.strip():
                return f"{name.strip()} {version.strip()}"[:32]
    except OSError:
        pass
    return None


@dataclass
class NextflowBackendConfig:
    profile: str  # "local" | "awsbatch"
    launch_dir: str  # local dir for configs, .nextflow.log, stdout
    work_dir: str  # local path or s3:// (awsbatch)
    tools_image: str
    execution: dict[str, Any] = field(default_factory=dict)  # executor/cpus/memory/queue/region
    nextflow_bin: str = "nextflow"
    main_nf: str = MAIN_NF
    timeout_seconds: int = 24 * 60 * 60
    poll_seconds: float = 5.0
    extra_args: list[str] = field(default_factory=list)  # e.g. ["-stub-run"] for CI

    @property
    def threads(self) -> int:
        return int(self.execution.get("cpus") or 4)

    @property
    def memory(self) -> str:
        return f"{int(self.execution.get('memory_gb') or 16)} GB"


class NextflowStageRunner:
    def __init__(
        self,
        cfg: NextflowBackendConfig,
        storage: Storage | None = None,
        should_cancel: Callable[[], bool] | None = None,
        popen: Callable[..., Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self.storage = storage or LocalStorage()
        self._should_cancel = should_cancel or (lambda: False)
        self._popen = popen

    # ── process control ────────────────────────────────────────────────────────

    def run_workflow(
        self, workflow: str, sample_id: str, output_dir: str, params: dict[str, Any]
    ) -> None:
        launch = os.path.join(self.cfg.launch_dir, workflow, sample_id)
        os.makedirs(launch, exist_ok=True)
        overrides = os.path.join(launch, "overrides.config")
        with open(overrides, "w") as fh:
            fh.write(build_config_overrides(self.cfg.execution))
            fh.write(f"\nworkDir = '{self.cfg.work_dir}'\n")

        cmd = [
            self.cfg.nextflow_bin,
            "-log",
            os.path.join(launch, ".nextflow.log"),
            "run",
            self.cfg.main_nf,
            "-profile",
            self.cfg.profile,
            "-c",
            overrides,
            "-work-dir",
            self.cfg.work_dir,
            "--workflow",
            workflow,
            "--sample_id",
            sample_id,
            "--output_dir",
            output_dir,
            "--tools_image",
            self.cfg.tools_image,
            "--threads",
            str(self.cfg.threads),
            "--memory",
            self.cfg.memory,
            *self.cfg.extra_args,
        ]
        for key, value in params.items():
            # resources come from the run's execution settings, not per-stage inputs
            if key != "threads" and value is not None and value != "":
                cmd += [f"--{key}", str(value)]

        stdout_path = os.path.join(launch, "nextflow.stdout")
        start = time.monotonic()
        with open(stdout_path, "wb") as out:
            popen = self._popen or subprocess.Popen
            proc = popen(cmd, stdout=out, stderr=subprocess.STDOUT, cwd=launch)
            while proc.poll() is None:
                if self._should_cancel():
                    proc.terminate()
                    try:
                        proc.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise NextflowCancelledError(f"nextflow {workflow} cancelled")
                if time.monotonic() - start > self.cfg.timeout_seconds:
                    proc.kill()
                    raise ToolExecutionError("nextflow", -9, "timed out", cmd)
                time.sleep(self.cfg.poll_seconds)
        if proc.returncode != 0:
            with open(stdout_path, "rb") as fh:
                tail = fh.read()[-2000:].decode("utf-8", errors="replace")
            raise ToolExecutionError("nextflow", proc.returncode, tail, cmd)

    def _require(self, path: str) -> str:
        if not self.storage.exists(path):
            raise ToolValidationError(
                "nextflow", "output", f"expected output {posixpath.basename(path)} not published"
            )
        return path

    def _out(self, output_dir: str, name: str) -> str:
        return self._require(self.storage.join(output_dir, name))

    def _version(self, output_dir: str, sample_id: str, tool: str, pinned: str) -> str | None:
        """Version reported by the process that ran (``<sid>.<tool>.version.txt``);
        falls back to the tools-image pin when the file is absent."""
        path = self.storage.join(output_dir, f"{sample_id}.{tool}.version.txt")
        if self.storage.exists(path):
            with open(self.storage.localize(path)) as fh:
                line = fh.readline().strip()
            if line:
                return line[:32]
        return pinned_version(pinned)

    # ── per-stage compute functions ────────────────────────────────────────────

    def compute_for(self, stage: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return {
            "qc": self.qc,
            "alignment": self.alignment,
            "quantification": self.quantification,
            "variant_calling": self.variant_calling,
        }[stage]

    def qc(self, inp: dict[str, Any]) -> dict[str, Any]:
        r1, r2 = (inp["fastq_paths"] + [None])[:2]
        out_dir = inp["output_dir"]
        self.run_workflow("qc", inp["sample_id"], out_dir, {"fastq_r1": r1, "fastq_r2": r2})
        html, zips, summary = [], [], {}
        for fq in inp["fastq_paths"]:
            stem = _sample_stem(fq)
            html.append(self._out(out_dir, f"{stem}_fastqc.html"))
            zip_path = self._out(out_dir, f"{stem}_fastqc.zip")
            zips.append(zip_path)
            summary.update(_read_zip_summary(self.storage.localize(zip_path)))
        return {
            "fastqc": FastQCOutput(
                report_html_paths=html,
                report_zip_paths=zips,
                summary=summary,
                tool_version=self._version(out_dir, inp["sample_id"], "fastqc", "FastQC"),
            )
        }

    def alignment(self, inp: dict[str, Any]) -> dict[str, Any]:
        sid, out_dir = inp["sample_id"], os.path.dirname(inp["output_prefix"])
        mode = inp.get("alignment_mode", "genome")
        self.run_workflow(
            "alignment",
            sid,
            out_dir,
            {
                "fastq_r1": inp["fastq_r1"],
                "fastq_r2": inp.get("fastq_r2"),
                "genome_dir": inp["genome_dir"],
                "alignment_mode": mode,
                "read_group": inp.get("read_group"),
            },
        )
        log_path = self._out(out_dir, f"{sid}_Log.final.out")
        with open(self.storage.localize(log_path)) as fh:
            stats = parse_star_log_final(fh.read())
        bam = self._out(out_dir, f"{sid}.sorted.bam")
        bai = self._out(out_dir, f"{sid}.sorted.bam.bai")
        tx_bam = (
            self._out(out_dir, f"{sid}_Aligned.toTranscriptome.out.bam")
            if mode != "genome"
            else None
        )
        star = STARAlignOutput(
            bam_path=bam,
            bam_index_path=bai,
            log_final_path=log_path,
            splice_junctions_path=self._out(out_dir, f"{sid}_SJ.out.tab"),
            transcriptome_bam_path=tx_bam,
            alignment_stats=stats,
            tool_version=self._version(out_dir, sid, "star", "STAR"),
        )
        samtools = SamtoolsOutput(
            sorted_bam_path=bam,
            bai_path=bai,
            flagstat={},
            tool_version=self._version(out_dir, sid, "samtools", "samtools"),
        )
        return {"star": star, "samtools": samtools}

    def quantification(self, inp: dict[str, Any]) -> dict[str, Any]:
        sid, out_dir, method = inp["sample_id"], inp["output_dir"], inp["quantification_method"]
        params: dict[str, Any] = {"quant_mode": method}
        if method == "salmon":
            params.update(
                fastq_r1=inp["fastq_r1"],
                fastq_r2=inp.get("fastq_r2"),
                salmon_index=inp["index_path"],
            )
        elif method == "rsem":
            params.update(bam=inp["bam_path"], rsem_reference=inp["rsem_reference"])
        else:
            params.update(bam=inp["bam_path"], gtf_path=inp["gtf_path"])
        self.run_workflow("quantification", sid, out_dir, params)

        if method == "salmon":
            base = self.storage.join(out_dir, sid)
            meta_path = self._require(self.storage.join(base, "aux_info", "meta_info.json"))
            with open(self.storage.localize(meta_path)) as fh:
                meta = parse_salmon_meta_info(json.load(fh))
            quant: Any = SalmonQuantOutput(
                quant_sf_path=self._require(self.storage.join(base, "quant.sf")),
                lib_format_counts_path=self.storage.join(base, "lib_format_counts.json"),
                meta_info_path=meta_path,
                inferred_lib_type=meta["inferred_lib_type"],
                mapping_rate=meta["mapping_rate"],
                tool_version=self._version(out_dir, sid, "salmon", "Salmon"),
            )
        elif method == "rsem":
            quant = RSEMOutput(
                genes_results_path=self._out(out_dir, f"{sid}.genes.results"),
                isoforms_results_path=self._out(out_dir, f"{sid}.isoforms.results"),
                stat_dir=self.storage.join(out_dir, f"{sid}.stat"),
                tool_version=self._version(out_dir, sid, "rsem", "RSEM"),
            )
        else:
            counts_path = self._out(out_dir, f"{sid}_counts.tsv")
            with open(self.storage.localize(counts_path)) as fh:
                stats = parse_htseq_counts(fh.read())
            quant = HTSeqOutput(
                counts_path=counts_path,
                total_reads=stats["total_reads"],
                counted_reads=stats["counted_reads"],
                no_feature_reads=stats["no_feature_reads"],
                ambiguous_reads=stats["ambiguous_reads"],
                tool_version=self._version(out_dir, sid, "htseq", "HTSeq"),
            )
        return {"quant": quant}

    def variant_calling(self, inp: dict[str, Any]) -> dict[str, Any]:
        sid, out_dir = inp["sample_id"], inp["output_dir"]
        self.run_workflow(
            "variant_calling",
            sid,
            out_dir,
            {
                "bam": inp["bam_path"],
                "bai": inp["bam_index_path"],
                "reference_fasta": inp["reference_fasta"],
            },
        )
        raw = self._out(out_dir, f"{sid}.raw.vcf.gz")
        filtered = self._out(out_dir, f"{sid}.filtered.vcf.gz")
        raw_counts = _count_vcf_variants(self.storage.localize(raw))
        counts = _count_vcf_variants(self.storage.localize(filtered))
        version = self._version(out_dir, sid, "gatk", "GATK")
        return {
            "haplotypecaller": GATKHaplotypeCallerOutput(
                vcf_path=raw,
                vcf_index_path=raw + ".tbi",
                variant_count=raw_counts["total_count"],
                tool_version=version,
            ),
            "filter": GATKVariantFilterOutput(
                filtered_vcf_path=filtered,
                filtered_vcf_index_path=filtered + ".tbi",
                pass_variant_count=counts["pass_count"],
                filtered_variant_count=counts["filtered_count"],
                tool_version=version,
            ),
        }
