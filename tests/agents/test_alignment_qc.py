"""``alignment_qc`` stage: RSeQC on the aligned BAM, after ``alignment`` (review finding #4).

RSeQC used to sit in ``qc``, which always runs before alignment, so it never had a BAM and
never ran. These tests cover the stage end to end: ordering and dependencies, stage inputs,
the BED12 gene model (genome BED or derived from the GTF once per run), DB rows, the Nextflow
and AWS Batch backends, dry runs and the results summary.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from src.agents.orchestrator import OrchestratorAgent, OrchestratorError
from src.agents.router import ALL_PIPELINE_STAGES
from src.agents.run_summary import results_markdown
from src.agents.stage_inputs import build_stage_inputs, load_pipeline_context
from src.db.enums import ArtifactType, StageName, StageStatus
from src.db.models.results import QCMetric
from src.db.models.run import AnalysisRun, Artifact, PipelineStage
from src.tools.qc.rseqc import RSeQCOutput
from tests.agents.test_stage_execution import (  # noqa: F401  (fixtures)
    RecordingEvents,
    _agent,
    _seed_run,
    db,
    tools,
)
from tests.tools.test_gtf_to_bed import GTF
from tests.tools.test_nextflow_stage_runner import FakeNextflow, _arg, _local_write

AQC = "src.agents.specialists.alignment_qc_agent.run_rseqc"


def _fake_rseqc(inp):  # type: ignore[no-untyped-def]
    rd = f"{inp.output_prefix}_read_distribution.txt"
    ie = f"{inp.output_prefix}_infer_experiment.txt"
    for path in (rd, ie):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("rseqc output\n")
    return RSeQCOutput(
        module_outputs={"read_distribution": rd, "infer_experiment": ie},
        read_distribution={"Total_Reads": 1000, "CDS_Exons": 800, "5'UTR_Exons": 50},
        infer_experiment_result={
            "library_type": "PairEnd",
            "undetermined": 0.01,
            "sense": 0.01,
            "antisense": 0.98,
            "strandedness": "reverse",
        },
        tool_version="RSeQC 5.0.1",
    )


@pytest.fixture
def rseqc():  # type: ignore[no-untyped-def]
    with patch(AQC, side_effect=_fake_rseqc) as m:
        yield m


def _write_gtf(tmp_path: Path) -> None:
    (tmp_path / "ref.gtf").write_text(GTF)


# ── ordering, dependencies, inputs ───────────────────────────────────────────


def test_stage_runs_after_alignment_before_quantification() -> None:
    i = ALL_PIPELINE_STAGES.index
    assert i("qc") < i("alignment") < i("alignment_qc") < i("quantification")


def test_requires_alignment(db, tmp_path) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["qc", "alignment_qc"])
    with pytest.raises(OrchestratorError, match="alignment"):
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))


def test_qc_stage_no_longer_takes_a_bam(db, tmp_path) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["qc"])
    ctx = load_pipeline_context(db, run_id, str(tmp_path / "out"))
    for inp in build_stage_inputs("qc", ctx, {}):
        assert "bam_path" not in inp and "bed_annotation_path" not in inp


def test_stage_inputs_use_alignment_bam_and_shared_gene_model(db, tmp_path) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["alignment", "alignment_qc"])
    ctx = load_pipeline_context(db, run_id, str(tmp_path / "out"))
    outs = {
        "alignment": {
            "samples": {
                s.id: {"output": {"sorted_bam_path": f"/b/{s.id}.bam", "sorted_bai_path": "/b/x"}}
                for s in ctx.samples
            }
        }
    }
    inputs = build_stage_inputs("alignment_qc", ctx, outs)
    assert len(inputs) == 4
    assert {i["bam_path"] for i in inputs} == {f"/b/{s.id}.bam" for s in ctx.samples}
    assert {i["gene_model_path"] for i in inputs} == {
        str(tmp_path / "out" / run_id / "alignment_qc" / "gene_model" / "genes.bed12")
    }
    assert all(i["bed_annotation_path"] is None for i in inputs)
    assert all(i["gtf_path"] == str(tmp_path / "ref.gtf") for i in inputs)


# ── local execution ──────────────────────────────────────────────────────────


def test_local_run_derives_bed_once_and_persists_metrics(db, tmp_path, tools, rseqc) -> None:  # noqa: F811
    _write_gtf(tmp_path)
    run_id = _seed_run(db, tmp_path, ["qc", "alignment", "alignment_qc"])
    final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))

    assert final["failed_stage"] is None, final["error_message"]
    assert final["completed_stages"] == ["qc", "alignment", "alignment_qc"]
    assert rseqc.call_count == 4
    beds = {c.args[0].bed_annotation_path for c in rseqc.call_args_list}
    assert len(beds) == 1
    bed = Path(beds.pop())
    assert bed.name == "genes.bed12" and "T1" in bed.read_text()
    bams = {c.args[0].bam_path for c in rseqc.call_args_list}
    assert all(p.endswith("_sorted.bam") for p in bams) and len(bams) == 4
    assert {tuple(c.args[0].modules) for c in rseqc.call_args_list} == {
        ("read_distribution", "infer_experiment")
    }

    rows = db.query(PipelineStage).filter_by(stage_name=StageName.alignment_qc).all()
    assert len(rows) == 4 and all(r.status == StageStatus.completed for r in rows)
    assert {r.tool_name for r in rows} == {"rseqc"} and rows[0].tool_version == "RSeQC 5.0.1"

    metrics = db.query(QCMetric).filter(QCMetric.stage_id.in_([r.id for r in rows])).all()
    by_name = {m.metric_name: m for m in metrics}
    assert by_name["rseqc_strandedness"].metric_value_str == "reverse"
    assert by_name["rseqc_ie_antisense"].metric_value == pytest.approx(0.98)
    assert by_name["rseqc_rd_cds_exons"].metric_value == 800
    assert "rseqc_rd_5'utr_exons" in by_name
    assert len(metrics) == 4 * 8

    reports = db.query(Artifact).filter_by(artifact_type=ArtifactType.rseqc_report).all()
    assert len(reports) == 8 and all(a.checksum_md5 for a in reports)

    summary = results_markdown(final)
    assert "Alignment QC (RSeQC): 4 sample(s)" in summary and "reverse" in summary


def test_genome_bed_is_used_without_conversion(db, tmp_path, tools, rseqc) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["alignment", "alignment_qc"])  # no GTF on disk
    run = db.get(AnalysisRun, uuid.UUID(run_id))
    run.genome.bed_annotation_path = "/ref/gencode.bed12"
    db.commit()
    final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
    assert final["failed_stage"] is None, final["error_message"]
    assert {c.args[0].bed_annotation_path for c in rseqc.call_args_list} == {"/ref/gencode.bed12"}
    assert not (tmp_path / "out" / run_id / "alignment_qc" / "gene_model").exists()


def test_dry_run_has_alignment_qc_fixture(db, tmp_path, tools, rseqc) -> None:  # noqa: F811
    run_id = _seed_run(db, tmp_path, ["alignment", "alignment_qc"])
    final = OrchestratorAgent(llm_client=None, dry_run=True).execute_run(db, run_id)
    assert final["completed_stages"] == ["alignment", "alignment_qc"]
    out = final["stage_outputs"]["alignment_qc"]
    assert out["mock"] is True
    assert out["output"]["infer_experiment_result"]["strandedness"] == "reverse"
    assert rseqc.call_count == 0


# ── Nextflow / AWS Batch ─────────────────────────────────────────────────────


def _set_executor(session, run_id: str, executor: str) -> None:  # type: ignore[no-untyped-def]
    run = session.get(AnalysisRun, uuid.UUID(run_id))
    run.run_config = {**run.run_config, "execution": {"executor": executor, "cpus": 2}}
    session.commit()


def test_nextflow_executor_runs_rseqc_workflow(db, tmp_path, tools, rseqc) -> None:  # noqa: F811
    _write_gtf(tmp_path)
    run_id = _seed_run(db, tmp_path, ["alignment", "alignment_qc"])
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
    qc_cmds = [c for c in fake.commands if _arg(c, "--workflow") == "alignment_qc"]
    assert len(qc_cmds) == 4 and rseqc.call_count == 0
    beds = {_arg(c, "--bed") for c in qc_cmds}
    assert len(beds) == 1 and Path(beds.pop()).read_text().startswith("chr1\t99\t500\tT1")
    assert all(_arg(c, "--bam").endswith(".sorted.bam") for c in qc_cmds)

    rows = db.query(PipelineStage).filter_by(stage_name=StageName.alignment_qc).all()
    assert {r.executor for r in rows} == {"nextflow"}
    strand = db.query(QCMetric).filter_by(metric_name="rseqc_strandedness").all()
    assert {m.metric_value_str for m in strand} == {"forward"}  # single-end "++,--" fixture


@mock_aws
def test_aws_batch_uploads_derived_bed_to_s3(db, tmp_path, tools, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setenv("S3_ARTIFACT_BUCKET", "rnaseq-bkt")
    monkeypatch.setenv("AWS_BATCH_JOB_QUEUE", "rnaseq-queue")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="rnaseq-bkt")
    s3.put_object(Bucket="rnaseq-bkt", Key="ref/g.gtf", Body=GTF.encode())

    def s3_write(uri: str, data: bytes) -> None:
        bucket, _, key = uri[5:].partition("/")
        s3.put_object(Bucket=bucket, Key=key, Body=data)

    run_id = _seed_run(db, tmp_path, ["alignment", "alignment_qc"])
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
    bed_uri = f"s3://rnaseq-bkt/runs/{run_id}/alignment_qc/gene_model/genes.bed12"
    qc_cmds = [c for c in fake.commands if _arg(c, "--workflow") == "alignment_qc"]
    assert {_arg(c, "--bed") for c in qc_cmds} == {bed_uri}
    key = bed_uri.removeprefix("s3://rnaseq-bkt/")
    body = s3.get_object(Bucket="rnaseq-bkt", Key=key)["Body"].read().decode()
    assert "T1" in body
    reports = db.query(Artifact).filter_by(artifact_type=ArtifactType.rseqc_report).all()
    assert reports and all(a.path.startswith("s3://") for a in reports)
