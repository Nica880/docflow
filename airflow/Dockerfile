# syntax=docker/dockerfile:1
# Airflow 2.10 + the DocFlow pipeline code.
#
# Why a separate virtualenv: Airflow 2.x pins SQLAlchemy < 2.0 (and many other libs through its
# constraints file) while DocFlow needs SQLAlchemy 2. Installing docflow into Airflow's own
# environment would break the scheduler. Instead docflow + its locked deps (uv.lock, incl. dbt)
# live in /app/.venv, built from the same /usr/local/bin/python3.12 interpreter, and the DAGs run
# pipeline code with `@task.external_python(python="/app/.venv/bin/python")`. Airflow's own
# environment is left untouched, and DAG files only import airflow (fast, DB-free parsing).

FROM ghcr.io/astral-sh/uv:0.13.10 AS uv

FROM apache/airflow:2.10.5-python3.12

USER root
COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_CACHE_DIR=/tmp/uv-cache \
    DOCFLOW_PYTHON=/app/.venv/bin/python

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra warehouse --no-install-project

COPY core ./core
COPY ingestion ./ingestion
COPY processing ./processing
COPY api ./api
COPY scripts ./scripts
COPY warehouse ./warehouse
COPY alembic.ini ./
COPY tests/fixtures ./tests/fixtures

RUN uv sync --frozen --no-dev --extra warehouse \
    && rm -rf /tmp/uv-cache \
    && mkdir -p /app/data/lake /app/data/warehouse /app/data/eval /app/data/reports \
    && chown -R airflow:0 /app \
    && chmod -R g+w /app/data /app/warehouse

USER airflow
WORKDIR /opt/airflow
COPY --chown=airflow:0 airflow/dags /opt/airflow/dags
