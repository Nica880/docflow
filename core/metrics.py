"""Prometheus metrics shared by the API and the workers."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

DOCS_PROCESSED = Counter(
    "docflow_docs_processed_total", "Documents processed per pipeline stage", ["stage", "outcome"]
)
EXTRACTIONS = Counter(
    "docflow_extractions_total", "LLM extractions by schema and outcome", ["schema", "outcome"]
)
EXTRACTION_LATENCY = Histogram(
    "docflow_extraction_latency_seconds",
    "LLM extraction latency (incl. repair retries)",
    ["model"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 40, 80, 160, 320),
)
QUEUE_DEPTH = Gauge("docflow_queue_depth", "Visible messages in the extraction queue")
AGENT_REQUESTS = Counter("docflow_agent_requests_total", "Q&A agent requests", ["outcome"])
