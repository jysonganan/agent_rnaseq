# TASK-02: Database Layer (SQLAlchemy ORM + Pydantic Schemas)

## Goal
Implement the SQLAlchemy ORM models, Alembic migrations, and Pydantic schemas for all entities defined in `docs/specs/data_models.md`.

## Requirements
- SQLAlchemy 2.x declarative models with full type annotations.
- Alembic `env.py` configured for SQLite (dev) and PostgreSQL (prod) via `DATABASE_URL` env var.
- Pydantic v2 schemas for all Create/Read/Update operations (separate from ORM models).
- `SessionLocal` factory and `get_db` FastAPI dependency.
- All enum types defined as Python `enum.Enum` and mapped to DB.

## Files to Create
```
src/db/
  __init__.py
  base.py              # DeclarativeBase, common mixin (id, created_at)
  models/
    __init__.py
    genome.py          # ReferenceGenome
    project.py         # Project, Sample, RunSample
    run.py             # AnalysisRun, PipelineStage, Artifact
    results.py         # QCMetric, DEGResult, GSEAResult, VariantCall
  session.py           # engine, SessionLocal, get_db
  enums.py             # all Enum definitions
alembic/
  env.py
  alembic.ini
  versions/
    0001_initial_schema.py
src/schemas/
  __init__.py
  genome.py
  project.py
  run.py
  results.py
  common.py            # shared base schemas (UUIDModel, TimestampMixin)
```

## Files to Edit
- `pyproject.toml` — add sqlalchemy, alembic, pydantic dependencies.

## Acceptance Criteria
- [ ] `alembic upgrade head` creates all tables on a fresh SQLite DB without errors.
- [ ] All ORM models can be imported without errors.
- [ ] All Pydantic schemas validate correct payloads and reject invalid ones (unit tested).
- [ ] `get_db` dependency yields a session and rolls back on exception.
- [ ] `ReferenceGenome`, `AnalysisRun`, `PipelineStage`, `DEGResult` each have at least 3 unit tests covering creation, validation, and constraint violations.
- [ ] Alembic migration is reversible (`alembic downgrade -1` succeeds).

## Definition of Done
All acceptance criteria pass. `pytest tests/db/` green.
