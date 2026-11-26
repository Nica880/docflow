# ADR-0007: Guardrails for the Q&A agent

- Status: accepted

## Decision
- The agent has three tools: `sql_query` (gold DuckDB), `semantic_search` (pgvector) and
  `get_filing_section`.
- SQL is parsed with sqlglot and rejected unless it is exactly one `SELECT`/set query over
  allow-listed gold tables: no DDL/DML, `ATTACH`, `COPY`, `PRAGMA`, table functions (`read_csv`,
  file paths), file/env functions, or schema-qualified names. A `LIMIT` (default 200) is enforced,
  the connection is read-only, and queries are interrupted after 5 s.
- A cheap domain check refuses clearly unrelated questions before any model call; an answer without
  at least one citation (filing + item) is converted into a refusal.

## Consequences
Prompt injection cannot escalate beyond reading allow-listed analytics tables. Refusals are tested
(`tests/unit/test_agent_eval.py`, Playwright).
