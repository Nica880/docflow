"""Guardrails for model-written SQL: one read-only SELECT over allow-listed gold tables."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

ALLOWED_TABLES: dict[str, str] = {
    "dim_company": "cik, name, ticker, sic_code, sector, n_filings, first_filed_at, last_filed_at",
    "dim_sector": "sector, n_companies",
    "fct_filings": "accession_no, cik, form_type, filed_at, period_end, fiscal_year, status, n_sections",
    "fct_financials": (
        "cik, ticker, company_name, sector, accession_no, fiscal_year, source ('llm' or 'xbrl'), "
        "revenue, net_income, operating_cash_flow (all in USD), min_confidence, is_reviewed"
    ),
    "fct_risk_mentions": (
        "cik, ticker, company_name, sector, accession_no, fiscal_year, category "
        "(ai_technology|cyber|regulatory|supply_chain|macro|competition|other), mentions"
    ),
    "fct_extraction_quality": (
        "model, prompt_version, schema_name, n_extractions, avg_confidence, avg_latency_ms, "
        "review_rate, xbrl_match_rate"
    ),
}

_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command,
    exp.Merge, exp.Copy, exp.Attach, exp.Detach, exp.Pragma, exp.Set, exp.Use, exp.Transaction,
    exp.Commit, exp.Rollback, exp.Into, exp.ReadCSV, exp.ReadParquet,
)  # fmt: skip
_FORBIDDEN_FUNCS = (
    "read_",
    "glob",
    "load",
    "install",
    "query",
    "sniff_",
    "getenv",
    "current_setting",
)


class UnsafeSQL(ValueError):
    pass


def validate_sql(sql: str, row_limit: int = 200) -> str:
    """Return a safe, LIMIT-capped version of `sql` or raise UnsafeSQL."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQL(f"could not parse SQL: {exc}") from exc
    if len(statements) != 1:
        raise UnsafeSQL("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeSQL("only SELECT queries are allowed")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN):
            raise UnsafeSQL(f"{type(node).__name__} is not allowed")
        if isinstance(node, exp.Func):
            fname = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if fname.startswith(_FORBIDDEN_FUNCS):
                raise UnsafeSQL(f"function '{fname}' is not allowed")
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):  # table functions
            raise UnsafeSQL("table functions are not allowed")
        if table.args.get("db") or table.args.get("catalog"):
            raise UnsafeSQL("schema-qualified tables are not allowed")
        name = table.name.lower()
        if name not in ALLOWED_TABLES and name not in ctes:
            raise UnsafeSQL(f"table '{name}' is not allowed; use: {', '.join(ALLOWED_TABLES)}")
    if isinstance(tree, exp.Select):
        limit = tree.args.get("limit")
        current = limit.expression if isinstance(limit, exp.Limit) else None
        if not (isinstance(current, exp.Literal) and int(current.this) <= row_limit):
            tree = tree.limit(row_limit)
    else:
        tree = exp.select("*").from_(tree.subquery("q")).limit(row_limit)
    return tree.sql(dialect="duckdb")


def schema_description() -> str:
    return "\n".join(f"- {t}({cols})" for t, cols in ALLOWED_TABLES.items())
