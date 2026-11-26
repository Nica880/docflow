"""parse_and_section: bronze filings -> silver sectioned text (failures go to quarantine)."""

from __future__ import annotations

from _common import DAG_KWARGS, DOCFLOW_PYTHON, RUN_ID_TEMPLATE
from airflow.decorators import dag, task
from airflow.models.param import Param


@dag(
    dag_id="parse_and_section",
    schedule="@hourly",
    description="Parse + section every filing still in status 'ingested'.",
    doc_md=__doc__,
    params={"limit": Param(None, type=["null", "integer"], description="Max filings per run")},
    **DAG_KWARGS,
)
def parse_and_section() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def parse_pending(limit: int | None, pipeline_run_id: str) -> dict:
        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from processing.silver import parse_pending as parse

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        # Idempotent: only filings with status 'ingested' are picked up.
        return parse(limit=int(limit) if limit else None, reparse=False, run_id=pipeline_run_id)

    parse_pending(limit="{{ params.limit }}", pipeline_run_id=RUN_ID_TEMPLATE)


parse_and_section()
