"""Tests for result endpoints (DE, GSEA, splicing, variants, QC)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.enums import (
    Aligner,
    AlignmentMode,
    PipelineType,
    RunStatus,
    SplicingEventType,
    StageName,
    StageStatus,
)
from src.db.models.results import DEGResult, GSEAResult, SplicingResult
from src.db.models.run import AnalysisRun, PipelineStage


def _make_run(session: Session, seed_data: dict) -> tuple[AnalysisRun, PipelineStage]:
    run = AnalysisRun(
        project_id=seed_data["project_id"],
        genome_id=seed_data["genome_id"],
        created_by=seed_data["api_key_id"],
        name="result-run",
        status=RunStatus.completed,
        pipeline_type=PipelineType.bulk_rnaseq,
        alignment_mode=AlignmentMode.genome,
        aligner=Aligner.star,
        run_config={},
    )
    session.add(run)
    session.flush()
    stage = PipelineStage(
        run_id=run.id,
        stage_name=StageName.differential_expression,
        status=StageStatus.completed,
        tool_name="deseq2",
    )
    session.add(stage)
    session.flush()
    return run, stage


class TestDEResults:
    def test_returns_200_for_known_run(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        with Session(db_engine) as session:
            run, stage = _make_run(session, seed_data)
            session.add(
                DEGResult(
                    stage_id=stage.id,
                    run_id=run.id,
                    contrast="treated_vs_control",
                    gene_id="ENSG00000001",
                )
            )
            session.commit()
            run_id = run.id

        r = client.get(
            f"/api/v1/runs/{run_id}/de?contrast=treated_vs_control",
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_contrast_filter_works(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        with Session(db_engine) as session:
            run, stage = _make_run(session, seed_data)
            session.add(
                DEGResult(
                    stage_id=stage.id,
                    run_id=run.id,
                    contrast="a_vs_b",
                    gene_id="ENSG0001",
                )
            )
            session.add(
                DEGResult(
                    stage_id=stage.id,
                    run_id=run.id,
                    contrast="c_vs_d",
                    gene_id="ENSG0002",
                )
            )
            session.commit()
            run_id = run.id

        r = client.get(f"/api/v1/runs/{run_id}/de?contrast=a_vs_b", headers=auth_headers)
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["gene_id"] == "ENSG0001"

    def test_paginated_response_shape(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        with Session(db_engine) as session:
            run, stage = _make_run(session, seed_data)
            session.commit()
            run_id = run.id

        r = client.get(f"/api/v1/runs/{run_id}/de?limit=20&offset=0", headers=auth_headers)
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    def test_unknown_run_returns_404(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.get(f"/api/v1/runs/{uuid.uuid4()}/de", headers=auth_headers)
        assert r.status_code == 404


class TestSplicingResults:
    def test_returns_200(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        with Session(db_engine) as session:
            run, stage = _make_run(session, seed_data)
            session.add(
                SplicingResult(
                    stage_id=stage.id,
                    run_id=run.id,
                    contrast="treated_vs_control",
                    event_type=SplicingEventType.SE,
                    gene_id="ENSG0001",
                )
            )
            session.commit()
            run_id = run.id

        r = client.get(f"/api/v1/runs/{run_id}/splicing", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["event_type"] == "SE"

    def test_unknown_run_returns_404(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.get(f"/api/v1/runs/{uuid.uuid4()}/splicing", headers=auth_headers)
        assert r.status_code == 404


class TestVariantResults:
    def test_returns_200_empty(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        with Session(db_engine) as session:
            run, stage = _make_run(session, seed_data)
            session.commit()
            run_id = run.id

        r = client.get(f"/api/v1/runs/{run_id}/variants", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_unknown_run_returns_404(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.get(f"/api/v1/runs/{uuid.uuid4()}/variants", headers=auth_headers)
        assert r.status_code == 404


class TestGSEAResults:
    def test_returns_200(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        with Session(db_engine) as session:
            run, stage = _make_run(session, seed_data)
            session.add(
                GSEAResult(
                    stage_id=stage.id,
                    run_id=run.id,
                    contrast="treated_vs_control",
                    pathway_id="R-HSA-69278",
                    pathway_name="Cell Cycle",
                    nes=1.5,
                )
            )
            session.commit()
            run_id = run.id

        r = client.get(f"/api/v1/runs/{run_id}/gsea", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["pathway_id"] == "R-HSA-69278"
