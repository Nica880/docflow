# DocFlow - developer entry points. POSIX make (macOS / Linux / CI).
#
# `make up` starts the CORE stack only (postgres, minio, localstack, migrate, api, worker, ui) to
# keep laptops light. Airflow (profile `airflow`) and OTel/Prometheus/Grafana (profile
# `observability`) are opt-in: `make up-all`, or `docker compose --profile <name> up -d`.

COMPOSE ?= docker compose
PROFILES_ALL = --profile airflow --profile observability
OTEL_ENDPOINT = http://otel-collector:4318
MODELS = qwen2.5:7b-instruct llama3.1:8b nomic-embed-text
TF_DIR = infra/terraform
SERVICE ?=

.DEFAULT_GOAL := help

.PHONY: help build up up-all down logs demo demo-offline test test-integration lint fmt dbt eval \
	e2e ui-dev tf-validate tf-apply-local pull-models

help: ## Show this help
	@echo "DocFlow make targets:"
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Default 'make up' = core stack (UI :8080, API :8000, MinIO :9001)."
	@echo "'make up-all' adds Airflow (:8081, admin/admin) + Grafana (:3000) / Prometheus (:9090)."
	@echo "Ollama runs natively on the host: 'make pull-models' once."

# migrate/api/worker share the docflow-app:local image. Building it from three services in
# parallel races on the image tag ("already exists"), so build it once via `api`, then start.
build: ## Build the app and UI images (app image once, shared by migrate/api/worker)
	$(COMPOSE) build api
	$(COMPOSE) build ui

up: build ## Build + start the core stack (postgres, minio, localstack, api, worker, ui)
	$(COMPOSE) up -d

up-all: build ## Core + Airflow + observability (OTel collector, Prometheus, Grafana), tracing on
	$(COMPOSE) --profile airflow build airflow
	OTEL_EXPORTER_OTLP_ENDPOINT=$(OTEL_ENDPOINT) $(COMPOSE) $(PROFILES_ALL) up -d

down: ## Stop every service (all profiles); volumes are kept
	$(COMPOSE) $(PROFILES_ALL) down

logs: ## Follow logs (all services, or SERVICE=api)
	$(COMPOSE) $(PROFILES_ALL) logs -f --tail=200 $(SERVICE)

demo: ## Small-mode end-to-end run against live EDGAR + Ollama (needs SEC_USER_AGENT in .env)
	$(COMPOSE) run --rm api docflow demo

demo-offline: ## Same demo, offline: recorded EDGAR fixtures + deterministic fake LLM
	$(COMPOSE) run --rm -e LLM_PROVIDER=fake -e EDGAR_FIXTURES_DIR=/app/tests/fixtures/edgar \
		api docflow demo

test: ## Unit tests
	uv run pytest

test-integration: ## Integration tests against the running stack (make up; host values from .env)
	uv run pytest -m integration -v

lint: ## ruff lint + format check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .

fmt: ## Auto-format and auto-fix
	uv run ruff format .
	uv run ruff check --fix .

dbt: ## Export the Parquet lake and run `dbt build` into gold (in the api container)
	$(COMPOSE) run --rm api sh -c "docflow export && docflow dbt --command build"

eval: ## Run the eval harness (both models + rules baseline) on the ground-truth set
	$(COMPOSE) run --rm api docflow eval

e2e: ## Playwright end-to-end tests
	cd ui && npm run e2e

ui-dev: ## Angular dev server on :4200 (proxies /api to localhost:8000)
	cd ui && npm start

tf-validate: ## terraform fmt check + init (no backend) + validate - works for real AWS, no cost
	cd $(TF_DIR) && terraform fmt -check -recursive
	cd $(TF_DIR) && terraform init -backend=false -input=false
	cd $(TF_DIR) && terraform validate

tf-apply-local: ## terraform apply against LocalStack (make up first)
	cd $(TF_DIR) && terraform init -input=false
	cd $(TF_DIR) && terraform apply -auto-approve -var-file=envs/localstack.tfvars

pull-models: ## Pull the Ollama models (run on the host)
	for m in $(MODELS); do ollama pull $$m || exit 1; done
