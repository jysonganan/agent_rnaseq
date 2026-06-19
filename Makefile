.PHONY: install test test-integration lint docker-up docker-down format typecheck

install:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest tests/ -v

test-integration:
	pytest tests/integration/ -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy src/

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down
