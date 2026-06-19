.PHONY: install test test-integration lint docker-up docker-down format typecheck docker-build docker-push

REGISTRY ?= 123456789.dkr.ecr.us-east-1.amazonaws.com
IMAGE_TAG ?= latest

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

docker-build:
	docker build -f docker/Dockerfile.api -t $(REGISTRY)/agent-rnaseq-api:$(IMAGE_TAG) .
	docker build -f docker/Dockerfile.streamlit -t $(REGISTRY)/agent-rnaseq-streamlit:$(IMAGE_TAG) .
	docker build -f docker/Dockerfile.tools -t $(REGISTRY)/agent-rnaseq-tools:$(IMAGE_TAG) .

docker-push:
	docker push $(REGISTRY)/agent-rnaseq-api:$(IMAGE_TAG)
	docker push $(REGISTRY)/agent-rnaseq-streamlit:$(IMAGE_TAG)
	docker push $(REGISTRY)/agent-rnaseq-tools:$(IMAGE_TAG)
