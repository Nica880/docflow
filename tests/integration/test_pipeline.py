"""End-to-end pipeline test against real services (Postgres+pgvector, S3, SQS).

Runs offline: EDGAR responses come from recorded fixtures and the LLM is the deterministic rules
provider. Start the stack with `make up` (or CI service containers), then:

    uv run pytest -m integration
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, object]]:
    data = tmp_path_factory.mktemp("data")
    env = {
        "LLM_PROVIDER": "fake",
        "EDGAR_FIXTURES_DIR": str(ROOT / "tests" / "fixtures" / "edgar"),
        "LAKE_DIR": str(data / "lake"),
        "WAREHOUSE_DIR": str(data / "warehouse"),
        "DBT_PROJECT_DIR": str(ROOT / "warehouse"),
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    from core.config import get_settings

    get_settings.cache_clear()

    from alembic import command
    from alembic.config import Config

    from core import queue, storage
    from core.cli import dbt
    from ingestion.bronze import ingest_tickers
    from ingestion.watchlist import DEMO
    from processing.embed import embed_sections
    from processing.export import export_lake
    from processing.ground_truth import seed_ground_truth
    from processing.invoices import generate_and_extract
    from processing.silver import parse_pending
    from processing.worker import enqueue_pending, run_worker

    cfg = Config(str(ROOT / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    storage.ensure_buckets()
    queue.queue_url.cache_clear()
    queue.queue_url()

    first = ingest_tickers(DEMO, max_workers=2)
    second = ingest_tickers(DEMO, max_workers=2)
    parsed = parse_pending()
    gt_rows = seed_ground_truth()
    enqueued = enqueue_pending(latest_per_company=1)
    worked = run_worker(max_messages=enqueued, idle_exit_s=10)
    invoices = generate_and_extract(3)
    chunks = embed_sections()
    counts = export_lake(mirror_to_s3=False)
    dbt("build")
    yield {
        "first": first,
        "second": second,
        "parsed": parsed,
        "gt_rows": gt_rows,
        "enqueued": enqueued,
        "worked": worked,
        "invoices": invoices,
        "chunks": chunks,
        "counts": counts,
    }
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    get_settings.cache_clear()


def test_ingestion_is_idempotent(pipeline: dict[str, object]) -> None:
    first, second = pipeline["first"], pipeline["second"]
    assert first.new == 8 and first.failed == 0  # type: ignore[attr-defined]
    assert second.new == 0 and second.skipped == 8  # type: ignore[attr-defined]


def test_pipeline_stages(pipeline: dict[str, object]) -> None:
    assert pipeline["parsed"] == {"parsed": 8, "quarantined": 0}
    assert pipeline["gt_rows"] > 0  # type: ignore[operator]
    assert pipeline["enqueued"] == 5
    assert pipeline["worked"] == {"processed": 5, "ok": 5}
    assert pipeline["chunks"] > 0  # type: ignore[operator]
    counts = pipeline["counts"]
    assert counts["financial_facts"] == 15 and counts["xbrl_facts"] > 0  # type: ignore[index]


def test_gold_matches_xbrl_for_apple(pipeline: dict[str, object]) -> None:
    from api import gold

    rows = gold.query(
        "SELECT source, revenue FROM fct_financials WHERE ticker = 'AAPL' AND fiscal_year = 2026"
    )
    by_source = {r["source"]: r["revenue"] for r in rows}
    assert by_source["llm"] == by_source["xbrl"] == 478_834_000_000


def test_api_and_agent(pipeline: dict[str, object]) -> None:
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    overview = client.get("/api/pipeline/overview").json()
    assert overview["totals"]["filings"] == 8
    assert overview["totals"]["open_reviews"] > 0

    task = client.get("/api/review").json()["items"][0]
    done = client.post(f"/api/review/{task['id']}", json={"action": "reject"}).json()
    assert done["status"] == "rejected"

    filing = client.get("/api/filings?cik=320193").json()["items"][0]
    section = client.get(f"/api/filings/{filing['accession_no']}/sections/1A").json()
    assert section["highlights"], "risk snippets should be highlighted in Item 1A"

    answer = client.post(
        "/api/qa", json={"question": "Which company had the highest revenue?"}
    ).json()
    assert not answer["refused"] and answer["citations"]
    assert "Apple" in answer["answer"].split("\n")[1]
    refused = client.post("/api/qa", json={"question": "What is the weather in Paris?"}).json()
    assert refused["refused"]
