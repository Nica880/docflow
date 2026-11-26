"""OpenTelemetry tracing setup + pipeline run bookkeeping (pipeline_runs table)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.config import get_settings

_tracing_ready = False


def setup_tracing(service_name: str | None = None) -> None:
    global _tracing_ready
    if _tracing_ready:
        return
    s = get_settings()
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name or s.service_name})
    )
    if s.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{s.otel_exporter_otlp_endpoint}/v1/traces")
            )
        )
    trace.set_tracer_provider(provider)
    _tracing_ready = True


def tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


@dataclass
class RunCounter:
    run_id: str
    docs_in: int = 0
    docs_ok: int = 0
    docs_quarantined: int = 0


@contextmanager
def pipeline_run(dag_id: str, run_id: str | None = None) -> Iterator[RunCounter]:
    """Record a pipeline run (start/finish + doc counters) in `pipeline_runs`."""
    from core.db import session_scope
    from core.models import PipelineRun

    rid = run_id or f"{dag_id}-{uuid.uuid4().hex[:12]}"
    counter = RunCounter(run_id=rid)
    with session_scope() as s:
        s.merge(
            PipelineRun(run_id=rid, dag_id=dag_id, started_at=datetime.now(UTC), status="running")
        )
    status = "success"
    try:
        with tracer("docflow.pipeline").start_as_current_span(dag_id) as span:
            span.set_attribute("docflow.run_id", rid)
            yield counter
            span.set_attribute("docflow.docs_in", counter.docs_in)
            span.set_attribute("docflow.docs_ok", counter.docs_ok)
    except Exception:
        status = "failed"
        raise
    finally:
        with session_scope() as s:
            run = s.get(PipelineRun, rid)
            if run is not None:
                run.finished_at = datetime.now(UTC)
                run.docs_in = counter.docs_in
                run.docs_ok = counter.docs_ok
                run.docs_quarantined = counter.docs_quarantined
                run.status = status
