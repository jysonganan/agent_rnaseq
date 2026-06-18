"""ORM model unit tests — creation, constraints, and relationships."""

import contextlib
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.enums import (
    Aligner,
    AlignmentMode,
    ArtifactType,
    Executor,
    PipelineType,
    RunStatus,
    SampleType,
    SplicingEventType,
    StageName,
    StageStatus,
)
from src.db.models import (
    AnalysisRun,
    APIKey,
    Artifact,
    DEGResult,
    PipelineStage,
    Project,
    ReferenceGenome,
    RunSample,
    Sample,
    ScRNAClusterResult,
    SplicingResult,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def make_api_key(db: Session, name: str = "test-key") -> APIKey:
    key = APIKey(
        key_hash="a" * 64,
        name=name,
        created_by="admin",
    )
    db.add(key)
    db.flush()
    return key


def make_genome(db: Session) -> ReferenceGenome:
    genome = ReferenceGenome(
        name="GRCh38_v43",
        species="homo_sapiens",
        build="GRCh38",
        fasta_path="/ref/GRCh38.fa",
        gtf_path="/ref/GRCh38.gtf",
    )
    db.add(genome)
    db.flush()
    return genome


def make_project(db: Session) -> Project:
    project = Project(name="Test Project", owner="user1")
    db.add(project)
    db.flush()
    return project


def make_sample(db: Session, project: Project) -> Sample:
    sample = Sample(
        project_id=project.id,
        name="ctrl_1",
        sample_type=SampleType.bulk_rnaseq,
        fastq_r1_path="/data/ctrl_1_R1.fastq.gz",
        is_paired_end=False,
    )
    db.add(sample)
    db.flush()
    return sample


def make_run(
    db: Session,
    project: Project,
    genome: ReferenceGenome,
    api_key: APIKey,
) -> AnalysisRun:
    run = AnalysisRun(
        project_id=project.id,
        genome_id=genome.id,
        created_by=api_key.id,
        name="test-run",
        pipeline_type=PipelineType.bulk_rnaseq,
        alignment_mode=AlignmentMode.genome,
        aligner=Aligner.star,
        run_config={"stages": ["qc"]},
    )
    db.add(run)
    db.flush()
    return run


def make_stage(db: Session, run: AnalysisRun) -> PipelineStage:
    stage = PipelineStage(
        run_id=run.id,
        stage_name=StageName.qc,
        status=StageStatus.pending,
        tool_name="fastqc",
    )
    db.add(stage)
    db.flush()
    return stage


# ── APIKey tests ───────────────────────────────────────────────────────────────


class TestAPIKey:
    def test_create_api_key(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        assert key.id is not None
        assert key.key_hash == "a" * 64
        assert key.is_active is True

    def test_key_hash_unique(self, db_session: Session) -> None:
        make_api_key(db_session, name="key1")
        with pytest.raises(IntegrityError):
            make_api_key(db_session, name="key2")  # same key_hash

    def test_revoked_key_is_inactive(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        key.revoked_at = datetime.now(UTC)
        db_session.flush()
        assert key.is_active is False

    def test_expired_key_is_inactive(self, db_session: Session) -> None:
        from datetime import timedelta

        key = make_api_key(db_session)
        key.expires_at = datetime.now(UTC) - timedelta(days=1)
        db_session.flush()
        assert key.is_active is False


# ── ReferenceGenome tests ──────────────────────────────────────────────────────


class TestReferenceGenome:
    def test_create_genome(self, db_session: Session) -> None:
        genome = make_genome(db_session)
        assert genome.id is not None
        assert genome.name == "GRCh38_v43"
        assert genome.created_at is not None

    def test_genome_name_unique(self, db_session: Session) -> None:
        make_genome(db_session)
        genome2 = ReferenceGenome(
            name="GRCh38_v43",  # duplicate
            species="homo_sapiens",
            build="GRCh38",
            fasta_path="/ref/other.fa",
            gtf_path="/ref/other.gtf",
        )
        db_session.add(genome2)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_optional_index_paths(self, db_session: Session) -> None:
        genome = ReferenceGenome(
            name="mm10",
            species="mus_musculus",
            build="mm10",
            fasta_path="/ref/mm10.fa",
            gtf_path="/ref/mm10.gtf",
            star_index_path="/idx/star_mm10",
        )
        db_session.add(genome)
        db_session.flush()
        assert genome.salmon_index_path is None
        assert genome.star_index_path == "/idx/star_mm10"

    def test_genome_fasta_required(self, db_session: Session) -> None:
        genome = ReferenceGenome(
            name="bad_genome",
            species="homo_sapiens",
            build="GRCh38",
            fasta_path=None,  # type: ignore[arg-type]
            gtf_path="/ref/GRCh38.gtf",
        )
        db_session.add(genome)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ── AnalysisRun tests ──────────────────────────────────────────────────────────


class TestAnalysisRun:
    def test_create_run(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        assert run.id is not None
        assert run.status == RunStatus.pending
        assert run.created_by == key.id

    def test_run_created_by_not_null(self, db_session: Session) -> None:
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = AnalysisRun(
            project_id=project.id,
            genome_id=genome.id,
            created_by=None,  # type: ignore[arg-type]
            name="bad-run",
            pipeline_type=PipelineType.bulk_rnaseq,
            alignment_mode=AlignmentMode.genome,
            aligner=Aligner.star,
            run_config={},
        )
        db_session.add(run)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_run_status_transitions(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        run.status = RunStatus.running
        run.started_at = datetime.now(UTC)
        db_session.flush()
        assert run.status == RunStatus.running


# ── PipelineStage tests ────────────────────────────────────────────────────────


class TestPipelineStage:
    def test_create_stage(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = make_stage(db_session, run)
        assert stage.id is not None
        assert stage.exit_code is None

    def test_exit_code_populated_on_failure(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = make_stage(db_session, run)
        stage.status = StageStatus.failed
        stage.exit_code = 1
        db_session.flush()
        assert stage.exit_code == 1

    def test_stage_tool_version_optional(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = PipelineStage(
            run_id=run.id,
            stage_name=StageName.alignment,
            status=StageStatus.pending,
            tool_name="star",
            tool_version="2.7.11a",
            executor=Executor.local,
        )
        db_session.add(stage)
        db_session.flush()
        assert stage.tool_version == "2.7.11a"


# ── DEGResult tests ────────────────────────────────────────────────────────────


class TestDEGResult:
    def _make_deg(self, db: Session) -> tuple[PipelineStage, DEGResult]:
        key = make_api_key(db)
        genome = make_genome(db)
        project = make_project(db)
        run = make_run(db, project, genome, key)
        stage = make_stage(db, run)
        deg = DEGResult(
            stage_id=stage.id,
            run_id=run.id,
            contrast="treatment_vs_control",
            gene_id="ENSG00000141510",
            gene_name="TP53",
            basemean=1200.5,
            log2_fold_change=2.3,
            pvalue=1.2e-8,
            padj=3.4e-6,
        )
        db.add(deg)
        db.flush()
        return stage, deg

    def test_create_deg_result(self, db_session: Session) -> None:
        _, deg = self._make_deg(db_session)
        assert deg.id is not None
        assert deg.contrast == "treatment_vs_control"
        assert deg.gene_name == "TP53"

    def test_deg_numeric_fields_nullable(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = make_stage(db_session, run)
        deg = DEGResult(
            stage_id=stage.id,
            run_id=run.id,
            contrast="treatment_vs_control",
            gene_id="ENSG00000000003",
        )
        db_session.add(deg)
        db_session.flush()
        assert deg.padj is None

    def test_deg_contrast_required(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = make_stage(db_session, run)
        deg = DEGResult(
            stage_id=stage.id,
            run_id=run.id,
            contrast=None,  # type: ignore[arg-type]
            gene_id="ENSG00000000001",
        )
        db_session.add(deg)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ── SplicingResult tests ────────────────────────────────────────────────────────


class TestSplicingResult:
    def test_create_splicing_result(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = make_stage(db_session, run)
        sr = SplicingResult(
            stage_id=stage.id,
            run_id=run.id,
            contrast="treatment_vs_control",
            event_type=SplicingEventType.SE,
            gene_id="ENSG00000105173",
            gene_name="PTBP1",
            inclusion_level_diff=-0.35,
            pvalue=1.1e-5,
            fdr=0.003,
        )
        db_session.add(sr)
        db_session.flush()
        assert sr.id is not None
        assert sr.event_type == SplicingEventType.SE


# ── ScRNAClusterResult tests ────────────────────────────────────────────────────


class TestScRNAClusterResult:
    def test_create_cluster_result(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        sample = make_sample(db_session, project)
        stage = PipelineStage(
            run_id=run.id,
            sample_id=sample.id,
            stage_name=StageName.scrna_seq,
            status=StageStatus.pending,
            tool_name="scanpy",
        )
        db_session.add(stage)
        db_session.flush()
        cr = ScRNAClusterResult(
            stage_id=stage.id,
            run_id=run.id,
            sample_id=sample.id,
            n_clusters=8,
            cluster_id=0,
            n_cells=450,
            top_marker_genes="CD3D,CD3E,TRAC",
        )
        db_session.add(cr)
        db_session.flush()
        assert cr.n_clusters == 8
        assert cr.top_marker_genes == "CD3D,CD3E,TRAC"


# ── RunSample join table ────────────────────────────────────────────────────────


class TestRunSample:
    def test_run_sample_association(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        sample = make_sample(db_session, project)
        run = make_run(db_session, project, genome, key)
        assoc = RunSample(run_id=run.id, sample_id=sample.id)
        db_session.add(assoc)
        db_session.flush()
        assert len(run.sample_associations) == 1


# ── Artifact tests ─────────────────────────────────────────────────────────────


class TestArtifact:
    def test_create_artifact(self, db_session: Session) -> None:
        key = make_api_key(db_session)
        genome = make_genome(db_session)
        project = make_project(db_session)
        run = make_run(db_session, project, genome, key)
        stage = make_stage(db_session, run)
        artifact = Artifact(
            stage_id=stage.id,
            run_id=run.id,
            artifact_type=ArtifactType.bam,
            path="/output/sample.bam",
            file_size_bytes=1_500_000_000,
            checksum_md5="d41d8cd98f00b204e9800998ecf8427e",
        )
        db_session.add(artifact)
        db_session.flush()
        assert artifact.id is not None
        assert artifact.file_size_bytes == 1_500_000_000


# ── get_db dependency ──────────────────────────────────────────────────────────


class TestGetDb:
    def test_get_db_yields_session(self) -> None:
        from src.db.session import get_db

        gen = get_db()
        session = next(gen)
        assert session is not None
        with contextlib.suppress(StopIteration):
            next(gen)

    def test_get_db_rolls_back_on_exception(self) -> None:
        from src.db.session import get_db

        gen = get_db()
        session = next(gen)
        assert session is not None
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("test error"))
