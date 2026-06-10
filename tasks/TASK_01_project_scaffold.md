# TASK-01: Project Scaffold & Dev Environment

## Goal
Bootstrap the repository layout, Python package structure, Docker dev environment, and CI configuration so all subsequent tasks have a stable foundation to build on.

## Requirements
- Python 3.11+ package with `pyproject.toml`.
- Docker Compose file that starts API, SQLite (dev), and Streamlit containers.
- `pre-commit` hooks: `ruff`, `mypy`, `pytest` smoke test.
- `.env.example` with all required environment variables documented.
- `Makefile` with targets: `install`, `test`, `lint`, `docker-up`, `docker-down`.

## Files to Create
```
pyproject.toml
Makefile
.env.example
.pre-commit-config.yaml
docker/
  Dockerfile.api
  Dockerfile.streamlit
  docker-compose.yml
src/
  __init__.py
  config.py              # Pydantic Settings from env vars
tests/
  __init__.py
  conftest.py
examples/
  scrnaseq/
    README.md
```

## Files to Edit
- `CLAUDE.md` — add local dev quickstart section.

## Acceptance Criteria
- [ ] `pip install -e ".[dev]"` succeeds.
- [ ] `docker-compose up -d` starts all services without errors.
- [ ] `make lint` passes with zero errors on the scaffold code.
- [ ] `make test` runs and reports 0 tests (no failures).
- [ ] `src/config.py` loads and validates all env vars; raises `ValidationError` on missing required vars.
- [ ] `.env.example` documents every variable in `config.py`.

## Definition of Done
All acceptance criteria pass. PR reviewed and merged to main.
