"""embed_sections: silver sections -> pgvector chunks (skips sections already embedded)."""

from __future__ import annotations

from _common import DAG_KWARGS, DOCFLOW_PYTHON
from airflow.decorators import dag, task
from airflow.models.param import Param


@dag(
    dag_id="embed_sections",
    schedule="@hourly",
    description="Embed not-yet-embedded sections with Ollama nomic-embed-text into pgvector.",
    doc_md=__doc__,
    params={
        "all_filings": Param(
            False, type="boolean", description="Embed every filing, not only the latest per company"
        )
    },
    **DAG_KWARGS,
)
def embed_sections() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def embed(all_filings: bool) -> dict:
        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from processing.embed import embed_sections as run_embed

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        all_flag = all_filings is True or str(all_filings).lower() == "true"
        return {"chunks": run_embed(latest_only=not all_flag)}

    embed(all_filings="{{ params.all_filings }}")


embed_sections()
