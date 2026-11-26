"""edgar_backfill: parameterized historical load, parallel by watch-list ticker chunks.

Trigger manually ("Trigger DAG w/ config"). Each mapped task ingests one chunk of tickers with
`ingestion.bronze.ingest_tickers`; at most BACKFILL_PARALLELISM chunks run at once and each gets
an equal share of the EDGAR request budget (SEC_MAX_RPS), so the DAG as a whole stays under the
SEC fair-access limit of 10 req/s.
"""

from __future__ import annotations

from _common import (
    BACKFILL_PARALLELISM,
    DAG_KWARGS,
    DOCFLOW_PYTHON,
    RUN_ID_TEMPLATE,
    SEC_TOTAL_RPS,
)
from airflow.decorators import dag, task
from airflow.models.param import Param


@dag(
    dag_id="edgar_backfill",
    schedule=None,
    description="Backfill N years of filings for the watch-list into bronze (manual trigger).",
    doc_md=__doc__,
    params={
        "years": Param(10, type="integer", minimum=1, maximum=30, description="Years back"),
        "forms": Param("10-K", type="string", description="Comma separated, e.g. 10-K,10-Q"),
        "max_filings": Param(None, type=["null", "integer"], description="Total cap"),
        "max_per_company": Param(None, type=["null", "integer"]),
        "chunk_size": Param(10, type="integer", minimum=1, description="Tickers per task"),
    },
    **DAG_KWARGS,
)
def edgar_backfill() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def plan_chunks(chunk_size: int, max_filings: int | None) -> list:
        import math

        from ingestion.watchlist import WATCHLIST

        size = max(1, int(chunk_size))
        chunks = [WATCHLIST[i : i + size] for i in range(0, len(WATCHLIST), size)]
        per_chunk = math.ceil(int(max_filings) / len(chunks)) if max_filings else None
        return [{"tickers": list(c), "max_filings": per_chunk} for c in chunks]

    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def ingest_chunk(
        chunk: dict,
        years: int,
        forms: str,
        max_per_company: int | None,
        sec_max_rps: float,
        pipeline_run_id: str,
    ) -> dict:
        import os
        from datetime import date

        # Must be set before core.config builds (and caches) the settings in this process.
        os.environ["SEC_MAX_RPS"] = str(sec_max_rps)

        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from ingestion.bronze import ingest_tickers

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        res = ingest_tickers(
            chunk["tickers"],
            forms=tuple(f.strip() for f in str(forms).split(",") if f.strip()),
            since=date(date.today().year - int(years), 1, 1),
            max_per_company=int(max_per_company) if max_per_company else None,
            max_filings=chunk.get("max_filings"),
            dag_id="edgar_backfill",
            run_id=pipeline_run_id,
        )
        return {
            "run_id": res.run_id,
            "tickers": chunk["tickers"],
            "new": res.new,
            "skipped": res.skipped,
            "failed": res.failed,
        }

    chunks = plan_chunks(
        chunk_size="{{ params.chunk_size }}", max_filings="{{ params.max_filings }}"
    )
    ingest_chunk.override(max_active_tis_per_dagrun=BACKFILL_PARALLELISM).partial(
        years="{{ params.years }}",
        forms="{{ params.forms }}",
        max_per_company="{{ params.max_per_company }}",
        sec_max_rps=SEC_TOTAL_RPS / BACKFILL_PARALLELISM,
        pipeline_run_id=RUN_ID_TEMPLATE,
    ).expand(chunk=chunks)


edgar_backfill()
