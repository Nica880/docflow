"""Shared DAG settings.

Pipeline code runs in the DocFlow virtualenv (`DOCFLOW_PYTHON`, see airflow/Dockerfile) through
`@task.external_python`, so DAG files import nothing from docflow and parse without a database.
Functions executed there are shipped as source: they must import everything they need inside
their body and cannot reference module globals.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
from typing import Any

DOCFLOW_PYTHON = os.environ.get("DOCFLOW_PYTHON", "/app/.venv/bin/python")

# pipeline_runs.run_id is VARCHAR(64).
_RUN_ID_MAX = 64

START_DATE = datetime(2024, 1, 1)

DEFAULT_ARGS: dict[str, Any] = {
    "owner": "docflow",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}

# Global EDGAR budget is 10 req/s; the backfill splits a safe 8 req/s across its parallel tasks.
SEC_TOTAL_RPS = 8.0
BACKFILL_PARALLELISM = 2


def docflow_run_id(dag_id: str, run_id: str, map_index: int | str | None = None) -> str:
    """Deterministic `pipeline_runs.run_id` for an Airflow (mapped) task instance.

    Same DAG run + task -> same id, so retries update the same row instead of adding new ones.
    """
    suffix = f"#{map_index}" if map_index not in (None, -1, "-1", "") else ""
    rid = f"{dag_id}__{run_id}{suffix}"
    if len(rid) <= _RUN_ID_MAX:
        return rid
    digest = hashlib.sha1(rid.encode(), usedforsecurity=False).hexdigest()[:16]
    return f"{dag_id[: _RUN_ID_MAX - len(digest) - 2]}__{digest}"


DAG_KWARGS: dict[str, Any] = {
    "start_date": START_DATE,
    "catchup": False,
    "max_active_runs": 1,
    "default_args": DEFAULT_ARGS,
    "user_defined_macros": {"docflow_run_id": docflow_run_id},
    # Keep ints/None from params and macros as Python objects in templated task arguments.
    "render_template_as_native_obj": True,
    "tags": ["docflow"],
}

# Jinja expression for templated task kwargs: unique per DAG run (+ map index).
RUN_ID_TEMPLATE = "{{ docflow_run_id(dag.dag_id, run_id, ti.map_index) }}"
