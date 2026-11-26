# Contributing / development notes

- Python 3.12 with [uv](https://docs.astral.sh/uv/): `uv sync --all-extras`.
- Every change must pass `make lint` (ruff, ruff format, mypy strict) and `make test`.
  Pipeline changes should also pass `make test-integration`, which needs the stack from `make up`.
- Run offline without Docker services for the network: `LLM_PROVIDER=fake` and
  `EDGAR_FIXTURES_DIR=tests/fixtures/edgar`.
- Refresh the recorded fixtures with `uv run python scripts/record_fixtures.py`. They are trimmed
  and gzipped real EDGAR responses.
- Schema changes need a new Alembic revision in `core/migrations/versions/`.
- Prompt changes need a new prompt version in `processing/prompts.py`, so eval runs stay comparable.
- Any non-obvious decision gets a short ADR in `docs/adr/`.
- Commits are small and each milestone ships with tests (see `docs/PLAN.md` §11).
