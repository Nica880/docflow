# ADR-0005: SQS work queue for extraction

- Status: accepted

## Decision
Extraction jobs (one per filing) go to an SQS queue (LocalStack locally) with a dead-letter queue
(`maxReceiveCount = 3`, visibility timeout 15 min). Workers long-poll, delete messages only after the
results are committed, and expose Prometheus metrics. `docflow extract` runs the same handler
in-process for laptops without the queue.

## Consequences
LLM calls are slow and bursty; the queue decouples Airflow scheduling from model throughput and lets
workers scale horizontally (one per GPU/host). Poison messages end up in the DLQ instead of looping.
