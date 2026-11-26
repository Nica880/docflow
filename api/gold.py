"""Read-only access to the gold DuckDB warehouse built by dbt."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import duckdb

from core.config import get_settings


class GoldUnavailable(RuntimeError):
    pass


@contextmanager
def gold_conn() -> Iterator[duckdb.DuckDBPyConnection]:
    path = get_settings().gold_db_path
    if not path.exists():
        raise GoldUnavailable(f"gold warehouse not built yet ({path}); run `make dbt`")
    try:
        conn = duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:  # e.g. dbt currently holds the write lock
        raise GoldUnavailable(str(exc)) from exc
    try:
        yield conn
    finally:
        conn.close()


def query(
    sql: str, params: list[Any] | None = None, timeout_s: float | None = None
) -> list[dict[str, Any]]:
    """Run a query; interrupts it after `timeout_s` (DuckDB has no statement timeout)."""
    with gold_conn() as conn:
        timer = None
        if timeout_s:
            timer = threading.Timer(timeout_s, conn.interrupt)
            timer.start()
        try:
            cur = conn.execute(sql, params or [])
            cols = [d[0] for d in cur.description or []]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        finally:
            if timer:
                timer.cancel()


def safe_query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Like `query`, but returns [] when the warehouse is not available (UI-friendly)."""
    try:
        return query(sql, params)
    except (GoldUnavailable, duckdb.CatalogException):
        return []
