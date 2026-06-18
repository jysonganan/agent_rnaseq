"""Pydantic schema unit tests — validation and rejection of invalid payloads."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.db.enums import Aligner, SampleType
from src.schemas.auth import APIKeyCreate, APIKeyCreatedResponse
from src.schemas.genome import ReferenceGenomeCreate
from src.schemas.project import ProjectCreate, ProjectRead, SampleCreate
from src.schemas.results import DEGResultRead, GSEAResultRead
from src.schemas.run import AnalysisRunCreate

# ── ReferenceGenome schemas ────────────────────────────────────────────────────


class TestReferenceGenomeSchema:
    def test_create_valid(self) -> None:
        g = ReferenceGenomeCreate(
            name="GRCh38_v43",
            species="homo_sapiens",
            build="GRCh38",
            fasta_path="/ref/GRCh38.fa",
            gtf_path="/ref/GRCh38.gtf",
        )
        assert g.name == "GRCh38_v43"
        assert g.star_index_path is None

    def test_rejects_missing_fasta(self) -> None:
        with pytest.raises(ValidationError):
            ReferenceGenomeCreate(
                name="GRCh38_v43",
                species="homo_sapiens",
                build="GRCh38",
                gtf_path="/ref/GRCh38.gtf",
            )  # type: ignore[call-arg]

    def test_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ReferenceGenomeCreate(
                name="x" * 65,
                species="homo_sapiens",
                build="GRCh38",
                fasta_path="/ref/fa",
                gtf_path="/ref/gtf",
            )


# ── Project schemas ────────────────────────────────────────────────────────────


class TestProjectSchema:
    def test_create_valid(self) -> None:
        p = ProjectCreate(name="My Experiment", owner="team_a")
        assert p.description is None

    def test_rejects_missing_owner(self) -> None:
        with pytest.raises(ValidationError):
            ProjectCreate(name="My Experiment")  # type: ignore[call-arg]

    def test_read_includes_timestamps(self) -> None:
        now = datetime.now(UTC)
        p = ProjectRead(
            id=uuid.uuid4(),
            name="My Experiment",
            owner="team_a",
            created_at=now,
            updated_at=now,
        )
        assert p.updated_at == now


# ── Sample schemas ─────────────────────────────────────────────────────────────


class TestSampleSchema:
    def test_create_valid(self) -> None:
        s = SampleCreate(
            name="ctrl_1",
            sample_type=SampleType.bulk_rnaseq,
            fastq_r1_path="/data/ctrl_1_R1.fastq.gz",
            is_paired_end=False,
        )
        assert s.sample_type == SampleType.bulk_rnaseq

    def test_invalid_sample_type(self) -> None:
        with pytest.raises(ValidationError):
            SampleCreate(
                name="ctrl_1",
                sample_type="invalid_type",  # type: ignore[arg-type]
                fastq_r1_path="/data/ctrl_1.fastq.gz",
                is_paired_end=False,
            )

    def test_metadata_alias(self) -> None:
        s = SampleCreate(
            name="ctrl_1",
            sample_type=SampleType.bulk_rnaseq,
            fastq_r1_path="/data/ctrl_1.fastq.gz",
            is_paired_end=True,
            metadata={"library": "poly_A"},
        )
        assert s.sample_metadata == {"library": "poly_A"}


# ── AnalysisRun schemas ────────────────────────────────────────────────────────


class TestAnalysisRunSchema:
    def _valid_payload(self) -> dict:
        return {
            "project_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "name": "test-run",
            "pipeline_type": "bulk_rnaseq",
            "sample_ids": [str(uuid.uuid4())],
            "stages": ["qc", "alignment"],
        }

    def test_create_valid(self) -> None:
        run = AnalysisRunCreate(**self._valid_payload())
        assert run.aligner == Aligner.star
        assert run.dry_run is False

    def test_empty_stages_rejected(self) -> None:
        payload = self._valid_payload()
        payload["stages"] = []
        with pytest.raises(ValidationError, match="stages must not be empty"):
            AnalysisRunCreate(**payload)

    def test_empty_sample_ids_rejected(self) -> None:
        payload = self._valid_payload()
        payload["sample_ids"] = []
        with pytest.raises(ValidationError, match="sample_ids must not be empty"):
            AnalysisRunCreate(**payload)

    def test_invalid_aligner_rejected(self) -> None:
        payload = self._valid_payload()
        payload["aligner"] = "bwa"
        with pytest.raises(ValidationError):
            AnalysisRunCreate(**payload)

    def test_execution_config_defaults(self) -> None:
        run = AnalysisRunCreate(**self._valid_payload())
        assert run.execution.cpus == 4
        assert run.execution.memory_gb == 16

    def test_execution_cpu_bounds(self) -> None:
        payload = self._valid_payload()
        payload["execution"] = {"cpus": 0}
        with pytest.raises(ValidationError):
            AnalysisRunCreate(**payload)


# ── DEGResult schema ───────────────────────────────────────────────────────────


class TestDEGResultSchema:
    def test_read_valid(self) -> None:
        d = DEGResultRead(
            id=uuid.uuid4(),
            stage_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            contrast="treatment_vs_control",
            gene_id="ENSG00000141510",
            gene_name="TP53",
            basemean=1200.5,
            log2_fold_change=2.3,
            pvalue=1.2e-8,
            padj=3.4e-6,
            lfcse=None,
            stat=None,
        )
        assert d.gene_name == "TP53"

    def test_missing_run_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DEGResultRead(
                id=uuid.uuid4(),
                stage_id=uuid.uuid4(),
                contrast="treatment_vs_control",
                gene_id="ENSG00000141510",
            )  # type: ignore[call-arg]


# ── GSEAResult schema ──────────────────────────────────────────────────────────


class TestGSEAResultSchema:
    def test_leading_edge_parsed_from_string(self) -> None:
        class FakeOrm:
            id = uuid.uuid4()
            stage_id = uuid.uuid4()
            run_id = uuid.uuid4()
            contrast = "treatment_vs_control"
            pathway_id = "R-HSA-109581"
            pathway_name = "Apoptosis"
            nes = 1.85
            pvalue = 0.001
            padj = 0.012
            leading_edge_genes = "TP53,BAX,BCL2"

        result = GSEAResultRead.model_validate(FakeOrm())
        assert result.leading_edge_genes == ["TP53", "BAX", "BCL2"]

    def test_empty_leading_edge(self) -> None:
        class FakeOrm:
            id = uuid.uuid4()
            stage_id = uuid.uuid4()
            run_id = uuid.uuid4()
            contrast = "treatment_vs_control"
            pathway_id = "R-HSA-109581"
            pathway_name = "Apoptosis"
            nes = None
            pvalue = None
            padj = None
            leading_edge_genes = None

        result = GSEAResultRead.model_validate(FakeOrm())
        assert result.leading_edge_genes == []


# ── APIKey schemas ─────────────────────────────────────────────────────────────


class TestAPIKeySchema:
    def test_create_valid(self) -> None:
        k = APIKeyCreate(name="ci-key")
        assert k.expires_at is None

    def test_name_required(self) -> None:
        with pytest.raises(ValidationError):
            APIKeyCreate()  # type: ignore[call-arg]

    def test_created_response_has_key_field(self) -> None:
        now = datetime.now(UTC)
        r = APIKeyCreatedResponse(
            id=uuid.uuid4(),
            name="ci-key",
            created_by="admin",
            created_at=now,
            expires_at=None,
            revoked_at=None,
            key="sk-raw-key-value",
        )
        assert r.key == "sk-raw-key-value"
