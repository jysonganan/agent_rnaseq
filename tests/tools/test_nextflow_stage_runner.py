"""Nextflow compute backend: unit tests + end-to-end runs for executor nextflow / aws_batch.

``FakeNextflow`` stands in for the ``nextflow`` process: it parses the command line the
runner builds and publishes the same files ``nextflow/main.nf`` publishes, either to a local
directory or (aws_batch) to S3 via moto.
"""

from __future__ import annotations

import gzip
import io
import os
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from src.agents.orchestrator import OrchestratorAgent, OrchestratorError
from src.db.enums import StageName, StageStatus
from src.db.models.run import AnalysisRun, Artifact, PipelineStage
from src.tools.base import ToolExecutionError, ToolValidationError
from src.tools.nextflow.stage_runner import (
    NextflowBackendConfig,
    NextflowCancelledError,
    NextflowStageRunner,
    pinned_version,
)
from src.tools.nextflow.storage import S3Storage
from tests.agents.test_stage_execution import (  # noqa: F401  (fixtures)
    BULK_STAGES,
    RecordingEvents,
    _seed_run,
    db,
    tools,
)

STAR_LOG = (
    "                          Number of input reads |\t1000\n"
    "                        Uniquely mapped reads % |\t90.00%\n"
)
VCF = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\n" + "".join(
    f"chr1\t{i}\t.\tA\tG\t50\t{'PASS' if i % 3 else 'SNPFilter'}\n" for i in range(1, 7)
)


def _fastqc_zip(stem: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"{stem}_fastqc/summary.txt",
            "PASS\tBasic Statistics\tx\nWARN\tPer sequence GC content\tx\n",
        )
    return buf.getvalue()


def _arg(cmd: list[str], name: str) -> str | None:
    return cmd[cmd.index(name) + 1] if name in cmd else None


class FakeNextflow:
    """Records commands and publishes outputs like nextflow/main.nf would."""

    def __init__(self, write: Callable[[str, bytes], None], fail_workflow: str | None = None):
        self.write = write
        self.fail_workflow = fail_workflow
        self.commands: list[list[str]] = []

    def __call__(self, cmd, stdout=None, stderr=None, cwd=None):  # type: ignore[no-untyped-def]
        self.commands.append(cmd)
        wf, sid, out = _arg(cmd, "--workflow"), _arg(cmd, "--sample_id"), _arg(cmd, "--output_dir")
        proc = MagicMock()
        proc.poll.return_value = 0
        proc.returncode = 0
        if wf == self.fail_workflow:
            stdout.write(b"ERROR ~ Error executing process > 'STAR_ALIGN'\n")
            proc.returncode = 1
            proc.poll.return_value = 1
            return proc
        j = lambda name: f"{out}/{name}"  # noqa: E731
        if wf == "qc":
            for fq in (_arg(cmd, "--fastq_r1"), _arg(cmd, "--fastq_r2")):
                if fq:
                    stem = os.path.basename(fq).replace(".fq.gz", "")
                    self.write(j(f"{stem}_fastqc.html"), b"<html/>")
                    self.write(j(f"{stem}_fastqc.zip"), _fastqc_zip(stem))
        elif wf == "alignment":
            self.write(j(f"{sid}_Log.final.out"), STAR_LOG.encode())
            self.write(j(f"{sid}_SJ.out.tab"), b"")
            self.write(j(f"{sid}.sorted.bam"), b"BAM" + sid.encode())
            self.write(j(f"{sid}.sorted.bam.bai"), b"BAI")
            if _arg(cmd, "--alignment_mode") != "genome":
                self.write(j(f"{sid}_Aligned.toTranscriptome.out.bam"), b"TX")
        elif wf == "quantification":
            self.write(j(f"{sid}_counts.tsv"), b"G1\t10\nG2\t20\n__no_feature\t5\n")
        elif wf == "variant_calling":
            for kind in ("raw", "filtered"):
                self.write(j(f"{sid}.{kind}.vcf.gz"), gzip.compress(VCF.encode()))
                self.write(j(f"{sid}.{kind}.vcf.gz.tbi"), b"")
        return proc


def _local_write(path: str, data: bytes) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


def _runner(tmp_path: Path, fake: FakeNextflow, **kw) -> NextflowStageRunner:  # type: ignore[no-untyped-def]
    cfg = NextflowBackendConfig(
        profile="local",
        launch_dir=str(tmp_path / "launch"),
        work_dir=str(tmp_path / "work"),
        tools_image="agent-rnaseq-tools:test",
        execution={"executor": "nextflow", "cpus": 2, "memory_gb": 4},
        poll_seconds=0,
    )
    return NextflowStageRunner(cfg, popen=fake, **kw)


# ── Unit tests ────────────────────────────────────────────────────────────────


class TestStageRunner:
    def test_command_line(self, tmp_path: Path) -> None:
        fake = FakeNextflow(_local_write)
        _runner(tmp_path, fake).qc(
            {
                "sample_id": "s1",
                "fastq_paths": ["/d/s1_R1.fq.gz"],
                "output_dir": str(tmp_path / "o"),
            }
        )
        cmd = fake.commands[0]
        assert cmd[:2] == ["nextflow", "-log"] and "run" in cmd
        assert _arg(cmd, "-profile") == "local"
        assert _arg(cmd, "--tools_image") == "agent-rnaseq-tools:test"
        assert "--fastq_r2" not in cmd  # None params are omitted
        overrides = Path(_arg(cmd, "-c")).read_text()
        assert "cpus = 2" in overrides and "workDir" in overrides

    def test_qc_outputs_validated_models(self, tmp_path: Path) -> None:
        out = _runner(tmp_path, FakeNextflow(_local_write)).qc(
            {
                "sample_id": "s1",
                "fastq_paths": ["/d/s1_R1.fq.gz", "/d/s1_R2.fq.gz"],
                "output_dir": str(tmp_path / "o"),
            }
        )["fastqc"]
        assert len(out.report_html_paths) == 2
        assert out.summary == {"Basic Statistics": "PASS", "Per sequence GC content": "WARN"}
        assert out.tool_version == pinned_version("FastQC") == "FastQC 0.12.1"

    def test_alignment_parses_star_log(self, tmp_path: Path) -> None:
        outs = _runner(tmp_path, FakeNextflow(_local_write)).alignment(
            {
                "sample_id": "s1",
                "fastq_r1": "/d/r1.fq.gz",
                "genome_dir": "/ref/star",
                "output_prefix": str(tmp_path / "o" / "S1_"),
                "alignment_mode": "both",
            }
        )
        assert outs["star"].alignment_stats["uniquely_mapped_pct"] == 90.0
        assert outs["star"].transcriptome_bam_path.endswith("_Aligned.toTranscriptome.out.bam")
        assert outs["samtools"].sorted_bam_path.endswith("s1.sorted.bam")

    def test_variant_counts_from_gz_vcf(self, tmp_path: Path) -> None:
        outs = _runner(tmp_path, FakeNextflow(_local_write)).variant_calling(
            {
                "sample_id": "s1",
                "bam_path": "/b.bam",
                "bam_index_path": "/b.bam.bai",
                "reference_fasta": "/ref/g.fa",
                "output_dir": str(tmp_path / "o"),
            }
        )
        assert outs["filter"].pass_variant_count == 4
        assert outs["filter"].filtered_variant_count == 2
        assert outs["haplotypecaller"].variant_count == 6

    def test_missing_published_output_rejected(self, tmp_path: Path) -> None:
        fake = FakeNextflow(lambda path, data: None)  # publishes nothing
        with pytest.raises(ToolValidationError):
            _runner(tmp_path, fake).qc(
                {"sample_id": "s1", "fastq_paths": ["/d/a.fq.gz"], "output_dir": str(tmp_path)}
            )

    def test_nonzero_exit_raises_with_log_tail(self, tmp_path: Path) -> None:
        fake = FakeNextflow(_local_write, fail_workflow="alignment")
        with pytest.raises(ToolExecutionError) as err:
            _runner(tmp_path, fake).alignment(
                {"sample_id": "s1", "fastq_r1": "/r1", "genome_dir": "/g", "output_prefix": "/o/x_"}
            )
        assert "STAR_ALIGN" in err.value.stderr

    def test_cancellation_terminates_process(self, tmp_path: Path) -> None:
        proc = MagicMock()
        proc.poll.return_value = None
        runner = _runner(tmp_path, lambda *a, **k: proc, should_cancel=lambda: True)
        with pytest.raises(NextflowCancelledError):
            runner.qc({"sample_id": "s", "fastq_paths": ["/a.fq"], "output_dir": str(tmp_path)})
        proc.terminate.assert_called_once()


# ── End-to-end through OrchestratorAgent.execute_run ─────────────────────────


def _set_executor(session, run_id: str, executor: str) -> None:  # type: ignore[no-untyped-def]
    run = session.get(AnalysisRun, uuid.UUID(run_id))
    run.run_config = {**run.run_config, "execution": {"executor": executor, "cpus": 2}}
    session.commit()


def test_nextflow_executor_end_to_end(db, tmp_path, tools) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, BULK_STAGES)
    _set_executor(db, run_id, "nextflow")
    fake = FakeNextflow(_local_write)
    with (
        patch("shutil.which", return_value="/usr/bin/nextflow"),
        patch("src.tools.nextflow.stage_runner.subprocess.Popen", fake),
        patch("src.tools.nextflow.stage_runner.time.sleep"),
    ):
        final = OrchestratorAgent(llm_client=None).execute_run(
            db, run_id, output_root=str(tmp_path / "out"), events=RecordingEvents()
        )
    assert final["failed_stage"] is None, final["error_message"]
    workflows = [_arg(c, "--workflow") for c in fake.commands]
    assert workflows == ["qc"] * 4 + ["alignment"] * 4 + ["quantification"] * 4
    # Heavy stages did not call the local tool wrappers; DE/GSEA stayed in the worker.
    assert tools["fastqc"].call_count == tools["star"].call_count == tools["htseq"].call_count == 0
    assert tools["deseq2"].call_count == 1 and tools["gsea"].call_count == 1
    # Same DB rows as a local run, with checksums for the locally published BAMs.
    rows = db.query(PipelineStage).filter_by(stage_name=StageName.alignment).all()
    assert len(rows) == 4 and all(r.status == StageStatus.completed for r in rows)
    assert rows[0].tool_version == "STAR 2.7.11b"
    assert {r.executor for r in rows} == {"nextflow"}
    de_row = db.query(PipelineStage).filter_by(stage_name=StageName.differential_expression).one()
    assert de_row.executor == "local"  # light stages stay in the worker
    assert all(a.checksum_md5 for a in db.query(Artifact).filter_by(artifact_type="bam"))
    # Counts published by Nextflow fed the DESeq2 matrix.
    matrix = tools["deseq2"].call_args.args[0].counts_matrix_path
    assert Path(matrix).read_text().splitlines()[1].startswith("G1,10,")


def test_nextflow_failure_marks_stage_failed(db, tmp_path, tools) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["alignment"])
    _set_executor(db, run_id, "nextflow")
    with (
        patch("shutil.which", return_value="/usr/bin/nextflow"),
        patch(
            "src.tools.nextflow.stage_runner.subprocess.Popen",
            FakeNextflow(_local_write, fail_workflow="alignment"),
        ),
    ):
        final = OrchestratorAgent(llm_client=None).execute_run(
            db, run_id, output_root=str(tmp_path / "out")
        )
    assert final["failed_stage"] == "alignment"
    assert "nextflow" in final["error_message"]
    row = db.query(PipelineStage).one()
    assert row.status == StageStatus.failed and row.executor == "nextflow"


def test_nextflow_missing_binary_refused(db, tmp_path) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["qc"])
    _set_executor(db, run_id, "nextflow")
    with patch("shutil.which", return_value=None), pytest.raises(OrchestratorError, match="PATH"):
        OrchestratorAgent(llm_client=None).execute_run(db, run_id, output_root=str(tmp_path))


def test_aws_batch_requires_s3_inputs(db, tmp_path, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setenv("S3_ARTIFACT_BUCKET", "bkt")
    monkeypatch.setenv("AWS_BATCH_JOB_QUEUE", "q")
    run_id = _seed_run(db, tmp_path, ["qc"])
    _set_executor(db, run_id, "aws_batch")
    with (
        patch("shutil.which", return_value="/usr/bin/nextflow"),
        pytest.raises(OrchestratorError, match="s3:// inputs"),
    ):
        OrchestratorAgent(llm_client=None).execute_run(db, run_id, output_root=str(tmp_path))


def test_aws_batch_requires_bucket_and_queue(db, tmp_path) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["qc"])
    _set_executor(db, run_id, "aws_batch")
    with (
        patch("shutil.which", return_value="/usr/bin/nextflow"),
        pytest.raises(OrchestratorError, match="S3_ARTIFACT_BUCKET"),
    ):
        OrchestratorAgent(llm_client=None).execute_run(db, run_id, output_root=str(tmp_path))


@mock_aws
def test_aws_batch_end_to_end_with_s3(db, tmp_path, tools, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setenv("S3_ARTIFACT_BUCKET", "rnaseq-bkt")
    monkeypatch.setenv("AWS_BATCH_JOB_QUEUE", "rnaseq-queue")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="rnaseq-bkt")

    def s3_write(uri: str, data: bytes) -> None:
        bucket, _, key = uri[5:].partition("/")
        s3.put_object(Bucket=bucket, Key=key, Body=data)

    run_id = _seed_run(db, tmp_path, ["alignment", "quantification", "differential_expression"])
    run = db.get(AnalysisRun, uuid.UUID(run_id))
    for assoc in run.sample_associations:
        assoc.sample.fastq_r1_path = f"s3://rnaseq-bkt/raw/{assoc.sample.name}_R1.fq.gz"
        assoc.sample.fastq_r2_path = None
    run.genome.fasta_path = "s3://rnaseq-bkt/ref/g.fa"
    run.genome.gtf_path = "s3://rnaseq-bkt/ref/g.gtf"
    run.genome.star_index_path = "s3://rnaseq-bkt/ref/star"
    db.commit()
    _set_executor(db, run_id, "aws_batch")

    fake = FakeNextflow(s3_write)
    with (
        patch("shutil.which", return_value="/usr/bin/nextflow"),
        patch("src.tools.nextflow.stage_runner.subprocess.Popen", fake),
    ):
        final = OrchestratorAgent(llm_client=None).execute_run(
            db, run_id, output_root=str(tmp_path / "out")
        )
    assert final["failed_stage"] is None, final["error_message"]
    cmd = fake.commands[0]
    assert _arg(cmd, "-profile") == "awsbatch"
    assert _arg(cmd, "--output_dir").startswith(f"s3://rnaseq-bkt/runs/{run_id}/alignment/")
    assert "rnaseq-queue" in Path(_arg(cmd, "-c")).read_text()
    # Artifacts reference S3; DE ran in the worker on downloaded counts files.
    bams = db.query(Artifact).filter_by(artifact_type="bam").all()
    assert bams and all(a.path.startswith("s3://") and a.checksum_md5 is None for a in bams)
    matrix = tools["deseq2"].call_args.args[0].counts_matrix_path
    assert not matrix.startswith("s3://") and "G1" in Path(matrix).read_text()


@mock_aws
def test_s3_storage_localizes_siblings_together(tmp_path) -> None:
    from src.aws.s3 import S3FileManager

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="bkt-x")
    s3.put_object(Bucket="bkt-x", Key="r/a.bam", Body=b"x")
    s3.put_object(Bucket="bkt-x", Key="r/a.bam.bai", Body=b"y")
    store = S3Storage(S3FileManager("bkt-x"), str(tmp_path))
    bam = store.localize("s3://bkt-x/r/a.bam")
    bai = store.localize("s3://bkt-x/r/a.bam.bai")
    assert os.path.dirname(bam) == os.path.dirname(bai)
    assert Path(bam).read_bytes() == b"x"
    assert store.exists("s3://bkt-x/r") and not store.exists("s3://bkt-x/zzz")


def test_version_file_overrides_pin_and_resources_passed(tmp_path: Path) -> None:
    def write_with_version(path: str, data: bytes) -> None:
        _local_write(path, data)
        if path.endswith("_Log.final.out"):
            _local_write(path.replace("_Log.final.out", ".star.version.txt"), b"STAR 2.7.11b\n")

    fake = FakeNextflow(write_with_version)
    runner = _runner(tmp_path, fake)
    runner.cfg.extra_args = ["-stub-run"]
    outs = runner.alignment(
        {
            "sample_id": "s1",
            "fastq_r1": "/d/r1.fq.gz",
            "genome_dir": "/ref/star",
            "output_prefix": str(tmp_path / "o" / "S1_"),
            "alignment_mode": "genome",
            "read_group": "ctrl_1",
            "threads": 99,  # ignored: resources come from the run's execution settings
        }
    )
    assert outs["star"].tool_version == "STAR 2.7.11b"
    cmd = fake.commands[0]
    assert _arg(cmd, "--threads") == "2" and _arg(cmd, "--memory") == "4 GB"
    assert _arg(cmd, "--read_group") == "ctrl_1" and "-stub-run" in cmd
    assert cmd.count("--threads") == 1
