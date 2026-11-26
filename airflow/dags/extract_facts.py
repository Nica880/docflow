"""extract_facts: queue parsed filings on SQS, then drain a batch with an extraction worker.

The long-running `worker` compose service consumes the same queue; this DAG's worker batch just
guarantees progress on a schedule and exits after 60 s without messages.
"""

from __future__ import annotations

from _common import DAG_KWARGS, DOCFLOW_PYTHON
from airflow.decorators import dag, task
from airflow.models.param import Param


@dag(
    dag_id="extract_facts",
    schedule="@hourly",
    description="Enqueue parsed filings for LLM extraction and run a worker batch.",
    doc_md=__doc__,
    params={
        "limit": Param(50, type=["null", "integer"], description="Max filings to enqueue"),
        "latest_per_company": Param(None, type=["null", "integer"]),
        "model": Param(None, type=["null", "string"], description="Default: LLM_MODEL"),
        "max_messages": Param(50, type="integer", minimum=1),
    },
    **DAG_KWARGS,
)
def extract_facts() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def enqueue(limit: int | None, latest_per_company: int | None, model: str | None) -> dict:
        from core import queue
        from core.config import get_settings
        from core.logging import configure_logging, get_logger
        from core.telemetry import setup_tracing
        from processing.worker import enqueue_pending

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        # Idempotency: filings stay 'parsed' until extracted, so only enqueue when the previous
        # batch is fully drained - otherwise a retry/next run would queue duplicates.
        depth = queue.depth()
        if depth["visible"] + depth["in_flight"] > 0:
            get_logger("dags.extract_facts").info("enqueue.skipped_queue_not_empty", **depth)
            return {"enqueued": 0, **depth}
        sent = enqueue_pending(
            limit=int(limit) if limit else None,
            latest_per_company=int(latest_per_company) if latest_per_company else None,
            model=model or None,
        )
        return {"enqueued": sent, **depth}

    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def run_worker_batch(max_messages: int) -> dict:
        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from processing.worker import run_worker

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        # Failed messages are not deleted: SQS redelivers them, then moves them to the DLQ.
        return run_worker(max_messages=int(max_messages), idle_exit_s=60)

    enqueue(
        limit="{{ params.limit }}",
        latest_per_company="{{ params.latest_per_company }}",
        model="{{ params.model }}",
    ) >> run_worker_batch(max_messages="{{ params.max_messages }}")


extract_facts()
