.PHONY: install test test-integration lint docker-up docker-down format typecheck docker-build docker-push frontend-build demo demo-record

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

frontend-build:
	cd frontend && npm ci && npm run build
	@echo "Frontend build complete: frontend/out/"

demo:
	python data/generate_data.py
	jupyter nbconvert --to notebook --execute --inplace notebooks/demo.ipynb \
	    --ExecutePreprocessor.timeout=120
	@echo ""
	@echo "Demo complete. Results in demo_output/streamlit_data/"
	@echo "Launch Streamlit:"
	@echo "  STREAMLIT_DATA_DIR=$$(pwd)/demo_output/streamlit_data streamlit run src/streamlit/app.py"

demo-record:
	@command -v asciinema >/dev/null || (echo "Install asciinema first: brew install asciinema" && exit 1)
	asciinema rec demo/demo.cast \
	    --title "agent_rnaseq — RNA-seq Pipeline Agent Demo" \
	    --command "bash demo/demo_commands.sh" \
	    --cols 120 --rows 35
	@if command -v agg >/dev/null; then \
	    agg demo/demo.cast demo/demo.gif --cols 120 --rows 35 --speed 1.5; \
	    echo "GIF written to demo/demo.gif"; \
	else \
	    echo "Install agg to convert to GIF: see demo/RECORDING_GUIDE.md"; \
	fi
