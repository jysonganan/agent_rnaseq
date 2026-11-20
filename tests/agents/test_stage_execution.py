"""Non-dry-run execution: OrchestratorAgent.execute_run → LangGraph → specialist agents.

Tool functions are patched at the specialist modules (no subprocesses), but everything
else is real: DB-backed PipelineContext, stage-input construction, count-matrix
merging, specialist DB writes, checkpointing, resume and cancellation.
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.agents.orchestrator import OrchestratorAgent, OrchestratorError
from src.agents.stage_inputs import (
    PipelineContext,
    load_pipeline_context,
    resolve_contrasts,
)
from src.api.background.runner import execute_run_sync
from src.db.base import Base
from src.db.enums import (
    Aligner,
    AlignmentMode,
    PipelineType,
    RunStatus,
    SampleType,
    StageName,
    StageStatus,
)
from src.db.models.auth import APIKey
from src.db.models.genome import ReferenceGenome
from src.db.models.project import Project, RunSample, Sample
from src.db.models.results import DEGResult, GSEAResult
from src.db.models.run import AnalysisRun, PipelineStage
from src.tools.alignment.samtools import SamtoolsOutput
from src.tools.alignment.star import STARAlignOutput
from src.tools.base import ToolExecutionError
from src.tools.de.deseq2 import DESeq2Output
from src.tools.de.parsers import DEContrastSummary
from src.tools.gsea.reactome import ReactomeGSEAOutput
from src.tools.qc.fastqc import FastQCOutput
from src.tools.qc.multiqc import MultiQCOutput
from src.tools.quantification.htseq import HTSeqOutput

BULK_STAGES = ["qc", "alignment", "quantification", "differential_expression", "gsea"]

_DE_CSV = (
    "gene_id,baseMean,log2FoldChange,lfcSE,stat,pvalue,padj\n"
    "G1,1000.0,2.5,0.3,8.3,1e-16,5e-15\n"
    "G2,500.0,-1.5,0.4,-3.75,0.0002,0.001\n"
)
_GSEA_CSV = "pathway_id,pathway_name,NES,pvalue,padj\nR-HSA-1,Signal transduction,2.1,0.001,0.01\n"


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_run(
    db: Session,
    tmp_path: Path,
    stages: list[str],
    conditions: tuple[str, ...] = ("control", "control", "treated", "treated"),
    de_contrasts: list[dict] | None = None,
) -> str:
    key = APIKey(key_hash=uuid.uuid4().hex, name="k", created_by="test")
    project = Project(name="p", owner="test")
    genome = ReferenceGenome(
        name="GRCh38",
        species="Homo sapiens",
        build="hg38",
        fasta_path=str(tmp_path / "ref.fa"),
        gtf_path=str(tmp_path / "ref.gtf"),
        star_index_path=str(tmp_path / "star"),
    )
    db.add_all([key, project, genome])
    db.flush()
    samples = [
        Sample(
            project_id=project.id,
            name=f"S{i}",
            sample_type=SampleType.bulk_rnaseq,
            condition=cond,
            fastq_r1_path=str(tmp_path / f"S{i}_R1.fq.gz"),
            fastq_r2_path=str(tmp_path / f"S{i}_R2.fq.gz"),
            is_paired_end=True,
        )
        for i, cond in enumerate(conditions)
    ]
    db.add_all(samples)
    db.flush()
    run = AnalysisRun(
        project_id=project.id,
        genome_id=genome.id,
        created_by=key.id,
        name="bulk",
        status=RunStatus.pending,
        pipeline_type=PipelineType.bulk_rnaseq,
        alignment_mode=AlignmentMode.genome,
        aligner=Aligner.star,
        run_config={
            "stages": stages,
            "de_contrasts": [{"numerator": "treated", "denominator": "control"}]
            if de_contrasts is None
            else de_contrasts,
            "execution": {"executor": "local", "cpus": 2},
        },
    )
    db.add(run)
    db.flush()
    for s in samples:
        db.add(RunSample(run_id=run.id, sample_id=s.id))
    db.commit()
    return str(run.id)


# ── Tool fakes ─────────────────────────────────────────────────────────────────


def _fake_star(inp):  # type: ignore[no-untyped-def]
    return STARAlignOutput(
        bam_path=inp.output_prefix + "Aligned.bam",
        bam_index_path=inp.output_prefix + "Aligned.bam.bai",
        log_final_path=inp.output_prefix + "Log.final.out",
        splice_junctions_path=inp.output_prefix + "SJ.out.tab",
        alignment_stats={},
        tool_version="STAR 2.7.11a",
    )


def _fake_samtools(inp):  # type: ignore[no-untyped-def]
    return SamtoolsOutput(
        sorted_bam_path=inp.output_prefix + ".bam",
        bai_path=inp.output_prefix + ".bam.bai",
        flagstat={},
        tool_version="samtools 1.17",
    )


def _fake_htseq(inp):  # type: ignore[no-untyped-def]
    """Write a real HTSeq-format file so build_count_matrix has something to merge."""
    Path(inp.output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(inp.output_path).write_text("G1\t10\nG2\t20\n__no_feature\t5\n")
    return HTSeqOutput(
        counts_path=inp.output_path,
        total_reads=35,
        counted_reads=30,
        no_feature_reads=5,
        ambiguous_reads=0,
        tool_version="HTSeq 2.0.2",
    )


def _fake_deseq2(inp):  # type: ignore[no-untyped-def]
    return DESeq2Output(
        results_paths={c.name: f"{inp.output_dir}/{c.name}_results.csv" for c in inp.contrasts},
        normalized_counts_path=f"{inp.output_dir}/normalized_counts.csv",
        size_factors_path=f"{inp.output_dir}/size_factors.csv",
        dispersion_plot_path=f"{inp.output_dir}/dispersion.pdf",
        pca_plot_path=f"{inp.output_dir}/pca.pdf",
        contrast_summaries={
            c.name: DEContrastSummary(
                total_genes=2, upregulated=1, downregulated=1, not_significant=0
            )
            for c in inp.contrasts
        },
        tool_version="DESeq2 1.42.0",
    )


def _fake_gsea(inp):  # type: ignore[no-untyped-def]
    return ReactomeGSEAOutput(
        results_path=f"{inp.output_dir}/gsea_results.csv",
        enrichment_plots_dir=f"{inp.output_dir}/plots",
        significant_pathway_count=1,
        tool_version="fgsea 1.26.0",
    )


@pytest.fixture
def tools():  # type: ignore[no-untyped-def]
    spec = "src.agents.specialists"
    with (
        patch(f"{spec}.qc_agent.run_fastqc") as fastqc,
        patch(f"{spec}.qc_agent.run_multiqc") as multiqc,
        patch(f"{spec}.alignment_agent.run_star_align", side_effect=_fake_star) as star,
        patch(f"{spec}.alignment_agent.run_samtools_sort_index", side_effect=_fake_samtools),
        patch(f"{spec}.quantification_agent.run_htseq_count", side_effect=_fake_htseq) as htseq,
        patch(f"{spec}.de_agent.run_deseq2", side_effect=_fake_deseq2) as deseq2,
        patch(f"{spec}.de_agent._read_deseq2_file", return_value=_DE_CSV),
        patch(f"{spec}.gsea_agent.run_reactome_gsea", side_effect=_fake_gsea) as gsea,
        patch(f"{spec}.gsea_agent._read_gsea_file", return_value=_GSEA_CSV),
    ):
        fastqc.return_value = FastQCOutput(
            report_html_paths=["/x/fastqc.html"],
            report_zip_paths=["/x/fastqc.zip"],
            summary={"Basic Statistics": "PASS"},
            tool_version="FastQC 0.12.1",
        )
        multiqc.return_value = MultiQCOutput(
            report_html_path="/x/multiqc.html", data_dir="/x/data", parsed_metrics={}
        )
        yield {"fastqc": fastqc, "star": star, "htseq": htseq, "deseq2": deseq2, "gsea": gsea}


def _agent() -> OrchestratorAgent:
    return OrchestratorAgent(llm_client=MagicMock())


class RecordingEvents:
    def __init__(self) -> None:
        self.frames: list[tuple] = []

    def stage_update(self, stage: str, status: str) -> None:
        self.frames.append(("stage_update", stage, status))

    def tool_call(self, tool_name: str, status: str, summary: str | None = None) -> None:
        self.frames.append(("tool_call", tool_name, status, summary))

    def log(self, level: str, stage, agent, message: str) -> None:  # type: ignore[no-untyped-def]
        self.frames.append(("log", level, stage, message))

    def run_error(self, message: str) -> None:
        self.frames.append(("error", message))


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestBulkExecution:
    def test_all_stages_dispatch_to_specialists(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, BULK_STAGES)
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))

        assert final["failed_stage"] is None, final["error_message"]
        assert final["completed_stages"] == BULK_STAGES
        assert tools["fastqc"].call_count == 4  # per sample
        assert tools["star"].call_count == 4
        assert tools["htseq"].call_count == 4
        assert tools["deseq2"].call_count == 1
        assert tools["gsea"].call_count == 1

        stages = db.query(PipelineStage).all()
        assert len(stages) == 4 + 4 + 4 + 1 + 1
        assert all(s.status == StageStatus.completed for s in stages)
        assert db.query(DEGResult).count() == 2
        assert db.query(GSEAResult).count() == 1

    def test_quantification_uses_sorted_bam_from_alignment(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment", "quantification"])
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        bam_paths = {c.args[0].bam_path for c in tools["htseq"].call_args_list}
        assert all(p.endswith("_sorted.bam") for p in bam_paths)
        assert len(bam_paths) == 4

    def test_de_gets_merged_matrix_and_user_contrast(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, BULK_STAGES[1:4])
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))

        de_inp = tools["deseq2"].call_args.args[0]
        assert [(c.numerator, c.denominator) for c in de_inp.contrasts] == [("treated", "control")]
        with open(de_inp.counts_matrix_path) as fh:
            rows = list(csv.reader(fh))
        assert rows[0][0] == "gene_id" and len(rows[0]) == 5
        assert [r[0] for r in rows[1:]] == ["G1", "G2"]  # __no_feature dropped
        with open(de_inp.sample_metadata_path) as fh:
            meta = list(csv.DictReader(fh))
        assert sorted(m["condition"] for m in meta) == ["control"] * 2 + ["treated"] * 2

    def test_checkpoint_written_to_agent_state(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["qc"])
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        assert run.agent_state["completed_stages"] == ["qc"]
        assert len(run.agent_state["stage_outputs"]["qc"]["samples"]) == 4


class TestFailureAndResume:
    def test_tool_failure_stops_pipeline_and_resume_skips_done(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, BULK_STAGES)
        tools["deseq2"].side_effect = ToolExecutionError("deseq2", 1, "boom")

        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] == "differential_expression"
        assert "boom" in final["error_message"]
        assert "gsea" not in final["completed_stages"]
        assert tools["gsea"].call_count == 0
        de_row = (
            db.query(PipelineStage).filter_by(stage_name=StageName.differential_expression).one()
        )
        assert de_row.status == StageStatus.failed

        # Resume: upstream stages must not re-run.
        tools["deseq2"].side_effect = _fake_deseq2
        star_calls = tools["star"].call_count
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] is None
        assert final["completed_stages"] == BULK_STAGES
        assert tools["star"].call_count == star_calls

    def test_non_tool_error_marks_stage_failed(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment"])
        tools["star"].side_effect = ValueError("bad output")
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] == "alignment"
        assert db.query(PipelineStage).one().status == StageStatus.failed

    def test_run_without_contrasts_is_refused_before_any_tool(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, BULK_STAGES[1:4], de_contrasts=[])
        with pytest.raises(OrchestratorError, match="at least one contrast"):
            _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert tools["star"].call_count == 0

    def test_cancelled_run_stops_before_next_stage(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["qc", "alignment"])

        def _cancel_then_fastqc(inp):  # type: ignore[no-untyped-def]
            db.get(AnalysisRun, uuid.UUID(run_id)).status = RunStatus.cancelled
            return tools["fastqc"].return_value

        tools["fastqc"].side_effect = _cancel_then_fastqc
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] in ("qc", "alignment")
        assert "cancelled" in final["error_message"]
        assert tools["star"].call_count == 0


class TestValidation:
    def test_dependency_violation_rejected(self, db, tmp_path) -> None:
        run_id = _seed_run(db, tmp_path, ["gsea"])
        with pytest.raises(OrchestratorError, match="requires"):
            _agent().execute_run(db, run_id, output_root=str(tmp_path))

    def test_non_local_executor_rejected(self, db, tmp_path) -> None:
        run_id = _seed_run(db, tmp_path, ["qc"])
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        run.run_config = {**run.run_config, "execution": {"executor": "aws_batch"}}
        db.commit()
        with pytest.raises(OrchestratorError, match="aws_batch"):
            _agent().execute_run(db, run_id, output_root=str(tmp_path))

    def test_explicit_contrasts_win(self, db, tmp_path) -> None:
        run_id = _seed_run(
            db,
            tmp_path,
            ["qc"],
            de_contrasts=[{"name": "c", "numerator": "control", "denominator": "treated"}],
        )
        ctx: PipelineContext = load_pipeline_context(db, run_id, str(tmp_path))
        assert resolve_contrasts(ctx) == [
            {"name": "c", "numerator": "control", "denominator": "treated"}
        ]

    def test_unknown_condition_refused(self, db, tmp_path) -> None:
        run_id = _seed_run(
            db,
            tmp_path,
            ["alignment", "quantification", "differential_expression"],
            de_contrasts=[{"numerator": "treated", "denominator": "wt"}],
        )
        with pytest.raises(OrchestratorError, match="'wt'"):
            _agent().execute_run(db, run_id, output_root=str(tmp_path))

    def test_splicing_requires_read_length(self, db, tmp_path) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment", "splicing"])
        with pytest.raises(OrchestratorError, match="read length"):
            _agent().execute_run(db, run_id, output_root=str(tmp_path))


class TestMultiCondition:
    CONDS = ("ctrl", "ctrl", "drugA", "drugA", "drugB", "drugB")
    CONTRASTS = [
        {"numerator": "drugA", "denominator": "ctrl"},
        {"numerator": "drugB", "denominator": "ctrl"},
        {"name": "A_vs_B", "numerator": "drugA", "denominator": "drugB"},
    ]

    def test_de_runs_every_user_contrast(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(
            db, tmp_path, BULK_STAGES[1:4], conditions=self.CONDS, de_contrasts=self.CONTRASTS
        )
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] is None, final["error_message"]
        de_inp = tools["deseq2"].call_args.args[0]
        assert [(c.name, c.numerator, c.denominator) for c in de_inp.contrasts] == [
            ("drugA_vs_ctrl", "drugA", "ctrl"),
            ("drugB_vs_ctrl", "drugB", "ctrl"),
            ("A_vs_B", "drugA", "drugB"),
        ]
        with open(de_inp.sample_metadata_path) as fh:
            assert {r["condition"] for r in csv.DictReader(fh)} == {"ctrl", "drugA", "drugB"}
        assert db.query(DEGResult).count() == 2 * 3

    def test_splicing_runs_once_per_contrast(self, db, tmp_path, tools) -> None:
        from src.tools.splicing.rmats import RMATSOutput

        run_id = _seed_run(
            db,
            tmp_path,
            ["alignment", "splicing"],
            conditions=self.CONDS,
            de_contrasts=self.CONTRASTS[:2],
        )
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        run.run_config = {**run.run_config, "read_length": 150}
        db.commit()
        with patch("src.agents.specialists.splicing_agent.run_rmats") as rmats:
            rmats.side_effect = lambda inp: RMATSOutput(
                output_dir=inp.output_dir,
                event_types=["SE"],
                significant_events_count={},
                summary_path=inp.output_dir + "/summary.txt",
            )
            final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] is None, final["error_message"]
        assert set(final["stage_outputs"]["splicing"]["contrasts"]) == {
            "drugA_vs_ctrl",
            "drugB_vs_ctrl",
        }
        calls = [c.args[0] for c in rmats.call_args_list]
        assert all(c.read_length == 150 for c in calls)
        assert all(len(c.bam_list_b1) == 2 and len(c.bam_list_b2) == 2 for c in calls)


class TestRunner:
    def test_execute_run_sync_sets_terminal_status(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["qc"])
        status = execute_run_sync(
            db, run_id, events=RecordingEvents(), output_root=str(tmp_path / "out")
        )
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        assert status == RunStatus.completed
        assert run.status == RunStatus.completed
        assert run.started_at is not None and run.completed_at is not None

    def test_execute_run_sync_records_failure(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment"])
        tools["star"].side_effect = ToolExecutionError("star", 1, "oom")
        assert (
            execute_run_sync(db, run_id, events=RecordingEvents(), output_root=str(tmp_path))
            == RunStatus.failed
        )
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        assert "oom" in run.error_message

    def test_execute_run_sync_skips_completed_run(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["qc"])
        db.get(AnalysisRun, uuid.UUID(run_id)).status = RunStatus.completed
        db.commit()
        assert (
            execute_run_sync(db, run_id, events=RecordingEvents(), output_root=str(tmp_path))
            == RunStatus.completed
        )
        assert tools["fastqc"].call_count == 0


class TestReviewFixes:
    def test_resume_skips_finished_samples_without_duplicate_rows(
        self, db, tmp_path, tools
    ) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment"])
        calls = {"n": 0}

        def _flaky(inp):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 3:
                raise ToolExecutionError("star", 137, "killed")
            return _fake_star(inp)

        tools["star"].side_effect = _flaky
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] == "alignment"
        assert len(final["stage_outputs"]["alignment"]["samples"]) == 2
        assert final["stage_outputs"]["alignment"]["partial"] is True

        tools["star"].side_effect = _fake_star
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] is None
        assert calls["n"] == 3 and tools["star"].call_count == 5  # only 2 re-attempted
        rows = db.query(PipelineStage).all()
        assert sorted(r.status for r in rows).count(StageStatus.completed) == 4
        assert [r.status for r in rows].count(StageStatus.failed) == 1
        assert len({r.sample_id for r in rows if r.status == StageStatus.completed}) == 4

    def test_failed_stage_rolls_back_partial_results_keeps_audit_row(
        self, db, tmp_path, tools
    ) -> None:
        run_id = _seed_run(db, tmp_path, BULK_STAGES[1:4])
        # DEG rows are added, then writing the artifact explodes.
        with patch(
            "src.agents.specialists.de_agent.DEAgent._write_artifact",
            side_effect=OSError("disk full at /data/x/y"),
        ):
            final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert final["failed_stage"] == "differential_expression"
        assert db.query(DEGResult).count() == 0
        de_row = (
            db.query(PipelineStage).filter_by(stage_name=StageName.differential_expression).one()
        )
        assert de_row.status == StageStatus.failed
        assert de_row.tool_name == "deseq2"
        assert de_row.input_params["contrasts"][0]["numerator"] == "treated"

    def test_error_message_is_sanitized(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment"])
        tools["star"].side_effect = ToolExecutionError(
            "star", 1, "cannot open /ref/secret/genome/SA"
        )
        final = _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        assert "/ref/secret" not in final["error_message"]
        assert "[PATH]" in final["error_message"]

    def test_audit_fields_recorded(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["qc"])
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        row = db.query(PipelineStage).first()
        assert row.started_at is not None and row.completed_at is not None
        assert row.executor == "local"
        assert row.input_params["fastq_paths"]

    def test_artifact_checksum_for_local_files(self, db, tmp_path, tools) -> None:
        from src.db.models.run import Artifact

        report = tmp_path / "fastqc.html"
        report.write_text("<html></html>")
        tools["fastqc"].return_value = tools["fastqc"].return_value.model_copy(
            update={"report_html_paths": [str(report)]}
        )
        run_id = _seed_run(db, tmp_path, ["qc"])
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"))
        art = db.query(Artifact).first()
        assert art.file_size_bytes == len("<html></html>")
        assert len(art.checksum_md5) == 32

    def test_events_published(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["qc", "alignment"])
        events = RecordingEvents()
        _agent().execute_run(db, run_id, output_root=str(tmp_path / "out"), events=events)
        updates = [f for f in events.frames if f[0] == "stage_update"]
        assert updates == [
            ("stage_update", "qc", "running"),
            ("stage_update", "qc", "completed"),
            ("stage_update", "alignment", "running"),
            ("stage_update", "alignment", "completed"),
        ]
        done_calls = [f for f in events.frames if f[0] == "tool_call" and f[2] == "completed"]
        assert done_calls[0][1] == "run_fastqc"
        logs = [f for f in events.frames if f[0] == "log"]
        assert all(f[2] in ("qc", "alignment") for f in logs)
        assert json.loads(done_calls[0][3]) == {"n_samples": 4}

    def test_runner_publishes_error_frame_on_failure(self, db, tmp_path, tools) -> None:
        run_id = _seed_run(db, tmp_path, ["alignment"])
        tools["star"].side_effect = ToolExecutionError("star", 1, "oom")
        events = RecordingEvents()
        execute_run_sync(db, run_id, events=events, output_root=str(tmp_path))
        assert ("error", "Stage failed: alignment") in events.frames


class TestOutputExcerpt:
    def test_numbers_kept_paths_dropped(self) -> None:
        from src.agents.run_events import output_excerpt

        out = {
            "output": {
                "results_paths": {"c": "/x/y.csv"},
                "contrast_summaries": {"c": {"upregulated": 3, "downregulated": 1}},
            }
        }
        assert json.loads(output_excerpt(out)) == {
            "contrast_summaries": {"c": {"downregulated": 1, "upregulated": 3}}
        }

    def test_redis_events_frames(self) -> None:
        from src.agents.run_events import RedisRunEvents

        redis = MagicMock()
        ev = RedisRunEvents(redis, "r1", conversation_id="c1", message_id="m1")
        ev.stage_update("qc", "running")
        ev.tool_call("QCAgent", "completed", '{"n_samples": 2}')
        ev.log("error", "qc", "QCAgent", "failed reading /a/b/c")
        ev.run_error("Stage failed: qc")
        sent = [(c.args[0], json.loads(c.args[1])) for c in redis.publish.call_args_list]
        assert sent[0] == (
            "conv:c1",
            {
                "type": "stage_update",
                "payload": {"run_id": "r1", "stage_name": "qc", "status": "running"},
            },
        )
        assert sent[1][1]["payload"]["message_id"] == "m1"
        assert sent[2][0] == "logs:r1" and "/a/b/c" not in sent[2][1]["message"]
        assert sent[3] == ("conv:c1", {"type": "error", "payload": {"message": "Stage failed: qc"}})

    def test_no_conversation_frames_for_api_runs(self) -> None:
        from src.agents.run_events import RedisRunEvents

        redis = MagicMock()
        ev = RedisRunEvents(redis, "r1")
        ev.stage_update("qc", "running")
        ev.log("info", "qc", "QCAgent", "hi")
        assert [c.args[0] for c in redis.publish.call_args_list] == ["logs:r1"]


def test_dry_run_flag_from_api_uses_mocks_not_tools(db, tmp_path, tools) -> None:
    run_id = _seed_run(db, tmp_path, ["qc", "alignment"])
    run = db.get(AnalysisRun, uuid.UUID(run_id))
    run.run_config = {**run.run_config, "dry_run": True}
    db.commit()
    status = execute_run_sync(db, run_id, events=RecordingEvents(), output_root=str(tmp_path))
    assert status == RunStatus.completed
    assert tools["fastqc"].call_count == 0 and tools["star"].call_count == 0
    assert db.query(PipelineStage).count() == 0
