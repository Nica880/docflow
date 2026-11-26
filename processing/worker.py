"""Extraction jobs over SQS: enqueue parsed filings, workers call the LLM and write results."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from core import queue
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.metrics import DOCS_PROCESSED, QUEUE_DEPTH
from core.models import Filing
from core.telemetry import pipeline_run
from processing.extract import extract_filing
from processing.schemas import FILING_SCHEMAS

log = get_logger(__name__)


def pending_accessions(
    limit: int | None = None, latest_per_company: int | None = None
) -> list[str]:
    with session_scope() as s:
        rows = s.execute(
            select(Filing.accession_no, Filing.cik)
            .where(Filing.status == "parsed", Filing.form_type != "INVOICE")
            .order_by(Filing.filed_at.desc())
        ).all()
    if latest_per_company:
        per: dict[int, int] = {}
        picked = []
        for acc, cik in rows:
            if per.get(cik, 0) < latest_per_company:
                picked.append(acc)
                per[cik] = per.get(cik, 0) + 1
        accs = picked
    else:
        accs = [acc for acc, _ in rows]
    return accs[:limit] if limit else accs


def enqueue_pending(
    limit: int | None = None,
    latest_per_company: int | None = None,
    model: str | None = None,
    schemas: tuple[str, ...] = FILING_SCHEMAS,
) -> int:
    bodies = [
        {"accession_no": acc, "schemas": list(schemas), "model": model}
        for acc in pending_accessions(limit, latest_per_company)
    ]
    sent = queue.send_batch(bodies)
    log.info("extract.enqueued", count=sent)
    return sent


def handle(body: dict[str, Any]) -> bool:
    outcomes = extract_filing(
        body["accession_no"], body.get("schemas") or FILING_SCHEMAS, body.get("model")
    )
    ok = all(o.ok for o in outcomes)
    DOCS_PROCESSED.labels(stage="extract", outcome="ok" if ok else "quarantined").inc()
    return ok


def run_worker(max_messages: int | None = None, idle_exit_s: float | None = None) -> dict[str, int]:
    """Long-poll SQS. Failed messages are not deleted -> retried, then moved to the DLQ."""
    done = ok = 0
    idle_since = time.monotonic()
    with pipeline_run("extract_facts") as run:
        while max_messages is None or done < max_messages:
            try:
                QUEUE_DEPTH.set(queue.depth()["visible"])
            except Exception as exc:  # metrics must never stop the worker
                log.debug("worker.depth_failed", error=str(exc))
            messages = queue.receive(max_messages=1, wait_s=5)
            if not messages:
                if idle_exit_s is not None and time.monotonic() - idle_since > idle_exit_s:
                    break
                continue
            idle_since = time.monotonic()
            for msg in messages:
                done += 1
                try:
                    success = handle(msg.body)
                    ok += success
                    queue.delete(msg)
                except Exception as exc:
                    log.exception("worker.failed", body=msg.body, error=str(exc))
            run.docs_in, run.docs_ok, run.docs_quarantined = done, ok, done - ok
    return {"processed": done, "ok": ok}


def extract_inline(
    limit: int | None = None,
    latest_per_company: int | None = None,
    model: str | None = None,
    schemas: tuple[str, ...] = FILING_SCHEMAS,
) -> dict[str, int]:
    """Same work as enqueue + worker, in-process (no SQS) - handy for laptops and tests."""
    accs = pending_accessions(limit, latest_per_company)
    ok = 0
    with pipeline_run("extract_facts") as run:
        run.docs_in = len(accs)
        for acc in accs:
            try:
                ok += handle({"accession_no": acc, "schemas": list(schemas), "model": model})
            except Exception as exc:
                log.exception("extract.failed", accession=acc, error=str(exc))
        run.docs_ok, run.docs_quarantined = ok, len(accs) - ok
    return {"processed": len(accs), "ok": ok}


def worker_main() -> None:
    from prometheus_client import start_http_server

    from core.logging import configure_logging
    from core.telemetry import setup_tracing

    s = get_settings()
    configure_logging(s.log_level)
    setup_tracing("docflow-worker")
    start_http_server(9100)
    log.info("worker.start", model=s.llm_model, provider=s.llm_provider)
    while True:
        run_worker(max_messages=50, idle_exit_s=60)
