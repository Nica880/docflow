"""edgar_ingest_daily: new 10-K filings for the watch-list, incremental by filing date."""

from __future__ import annotations

from _common import DAG_KWARGS, DOCFLOW_PYTHON, RUN_ID_TEMPLATE
from airflow.decorators import dag, task


@dag(
    dag_id="edgar_ingest_daily",
    schedule="@daily",
    description="Watch-list filings since (logical date - 1 day) -> bronze (idempotent).",
    doc_md=__doc__,
    **DAG_KWARGS,
)
def edgar_ingest_daily() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def ingest_watchlist(since: str, pipeline_run_id: str) -> dict:
        from datetime import date

        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from ingestion.bronze import ingest_tickers
        from ingestion.watchlist import WATCHLIST

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        # Re-runs are safe: bronze dedupes on accession number + checksum.
        res = ingest_tickers(
            WATCHLIST,
            forms=("10-K",),
            since=date.fromisoformat(str(since)),
            dag_id="edgar_ingest_daily",
            run_id=pipeline_run_id,
        )
        return {
            "run_id": res.run_id,
            "companies": res.companies,
            "new": res.new,
            "skipped": res.skipped,
            "failed": res.failed,
        }

    # The @daily run for logical date D starts at D+1, so this covers the last two days.
    ingest_watchlist(since="{{ macros.ds_add(ds, -1) }}", pipeline_run_id=RUN_ID_TEMPLATE)


edgar_ingest_daily()
