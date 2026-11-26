# ADR-0002: Medallion layers, Parquet lake and DuckDB gold

- Status: accepted

## Context
Operational state (filings, extractions, review queue) needs transactions and concurrent writers;
analytics needs fast scans, tests and documentation.

## Decision
- **Bronze**: raw documents in S3 (`{cik}/{accession}/{document}` + `.meta.json`), manifest rows in
  Postgres keyed by accession number + SHA-256 checksum, so re-runs never duplicate or re-download.
- **Silver**: per-item section text (S3 objects + versioned Parquet, `sections/v1/...`) and
  extractions with per-field confidence, model and prompt version.
- **Gold**: `docflow export` snapshots Postgres + flattened facts to Parquet; dbt-duckdb builds
  staging → intermediate → marts into a single `gold.duckdb`, which the API opens read-only.

## Consequences
- dbt runs against files, not the OLTP database: no load on Postgres, reproducible builds.
- Gold is a batch snapshot (minutes stale), acceptable for analytics; the review queue reads Postgres.
- DuckDB allows one writer: the API retries/gracefully degrades while `dbt build` holds the lock.
