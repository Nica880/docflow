"""Agent tools. Each returns (data for the model, citations for the answer)."""

from __future__ import annotations

import json
from typing import Any

from api import gold
from api.agent.sql_guard import UnsafeSQL, schema_description, validate_sql
from api.schemas import Citation
from core.config import get_settings
from processing.embed import semantic_search
from processing.silver import load_section_text

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "sql_query",
            "description": (
                "Run ONE read-only DuckDB SELECT over the gold warehouse. Tables:\n"
                + schema_description()
                + "\nAmounts are in USD. Prefer source='llm' in fct_financials."
            ),
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Semantic search over 10-K section text (Items 1, 1A, 1C, 7, 7A).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "ticker": {"type": "string", "description": "optional ticker filter"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_filing_section",
            "description": "Read the text of one section (item) of one filing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accession_no": {"type": "string"},
                    "item": {"type": "string", "description": "e.g. 1A, 7, 8"},
                },
                "required": ["accession_no", "item"],
            },
        },
    },
]


def _snip(text: str, n: int = 280) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def _fmt_value(v: Any) -> str:
    if isinstance(v, float) and abs(v) >= 1e6:
        return f"${v / 1e9:,.1f}B" if abs(v) >= 1e9 else f"${v / 1e6:,.1f}M"
    return str(v)


def sql_query(sql: str) -> tuple[list[dict[str, Any]], list[Citation]]:
    s = get_settings()
    safe = validate_sql(sql, s.sql_row_limit)
    rows = gold.query(safe, timeout_s=s.sql_timeout_s)
    citations: list[Citation] = []
    seen: set[str] = set()
    for r in rows:
        acc = r.get("accession_no")
        if acc and acc not in seen and len(citations) < 5:
            seen.add(acc)
            item = "1A" if "category" in r else "8"
            label = ", ".join(
                f"{k}={_fmt_value(v)}"
                for k, v in r.items()
                if k not in ("accession_no", "cik") and v is not None
            )
            citations.append(
                Citation(
                    accession_no=acc, item=item, company=r.get("company_name"), snippet=_snip(label)
                )
            )
    return rows, citations


def search(
    query: str, ticker: str | None = None, k: int = 5
) -> tuple[list[dict[str, Any]], list[Citation]]:
    hits = semantic_search(query, k=k, ticker=ticker)
    data = [
        {
            "accession_no": h.accession_no,
            "item": h.item,
            "company": h.company,
            "filed_at": h.filed_at,
            "score": h.score,
            "text": _snip(h.text, 900),
        }
        for h in hits
    ]
    cites = [
        Citation(accession_no=h.accession_no, item=h.item, company=h.company, snippet=_snip(h.text))
        for h in hits
    ]
    return data, cites


def get_section(
    accession_no: str, item: str, max_chars: int = 4000
) -> tuple[dict[str, Any], list[Citation]]:
    text, title = load_section_text(accession_no, item.upper())
    return (
        {"accession_no": accession_no, "item": item, "title": title, "text": text[:max_chars]},
        [Citation(accession_no=accession_no, item=item.upper(), company=None, snippet=_snip(text))],
    )


def run_tool(name: str, args: dict[str, Any]) -> tuple[str, list[Citation]]:
    """Execute a tool by name; errors are returned to the model as text (so it can recover)."""
    try:
        if name == "sql_query":
            rows, cites = sql_query(str(args.get("sql", "")))
            return json.dumps(rows[:50], default=str), cites
        if name == "semantic_search":
            data, cites = search(str(args.get("query", "")), args.get("ticker") or None)
            return json.dumps(data, default=str), cites
        if name == "get_filing_section":
            sec, cites = get_section(str(args["accession_no"]), str(args["item"]))
            return json.dumps(sec), cites
        return f"error: unknown tool {name}", []
    except UnsafeSQL as exc:
        return f"error: unsafe SQL rejected: {exc}", []
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}", []
