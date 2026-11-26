# syntax=docker/dockerfile:1
# DocFlow application image: API, extraction worker, CLI (`docflow ...`) and dbt.

FROM ghcr.io/astral-sh/uv:0.13.10 AS uv

FROM python:3.12-slim

COPY --from=uv /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

# Same uid/gid as the Airflow image (50000:0) so both can write the shared `docflow-data` volume.
RUN useradd --uid 50000 --gid 0 --create-home --shell /usr/sbin/nologin docflow

WORKDIR /app

# Dependencies first (cached layer), then the project itself (editable, so alembic.ini and
# the dbt project resolve relative to /app).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra warehouse --no-install-project

COPY core ./core
COPY ingestion ./ingestion
COPY processing ./processing
COPY api ./api
COPY scripts ./scripts
COPY warehouse ./warehouse
COPY alembic.ini ./
COPY tests/fixtures ./tests/fixtures

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra warehouse \
    && mkdir -p /app/data/lake /app/data/warehouse /app/docs/eval \
    && chown -R 50000:0 /app/data /app/docs /app/warehouse \
    && chmod -R g+w /app/data /app/docs /app/warehouse

USER 50000

EXPOSE 8000 9100
CMD ["docflow", "api"]
