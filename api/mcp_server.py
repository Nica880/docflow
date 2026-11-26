"""DocFlow MCP server (stdio): exposes the warehouse and filings to any MCP client.

    uv run docflow mcp        # or: python -m api.mcp_server

Claude Desktop config example: see docs/mcp.md.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from api import gold
from processing.embed import semantic_search
from processing.silver import load_section_text

mcp = MCPServer(
    "docflow", instructions="Query SEC 10-K filings, extracted financials and risk trends."
)


@mcp.tool()
def search_filings(query: str, ticker: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Semantic search over 10-K sections (business, risk factors, cybersecurity, MD&A).
    Returns passages with accession number, item, company and similarity score."""
    hits = semantic_search(query, k=max(1, min(limit, 20)), ticker=ticker)
    return [
        {
            "accession_no": h.accession_no,
            "item": h.item,
            "company": h.company,
            "ticker": h.ticker,
            "filed_at": h.filed_at,
            "score": h.score,
            "text": h.text[:1200],
        }
        for h in hits
    ]


@mcp.tool()
def get_company_financials(ticker: str) -> list[dict[str, Any]]:
    """Revenue, net income and operating cash flow (USD) by fiscal year for a ticker,
    both as extracted by the LLM (source='llm') and as reported in XBRL (source='xbrl')."""
    return gold.query(
        "SELECT company_name, fiscal_year, source, revenue, net_income, operating_cash_flow, "
        "accession_no FROM fct_financials WHERE upper(ticker) = upper(?) ORDER BY fiscal_year, source",
        [ticker],
    )


@mcp.tool()
def get_risk_trends(ticker: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
    """Risk-factor mentions per fiscal year and category (ai_technology, cyber, regulatory,
    supply_chain, macro, competition, other), optionally filtered by ticker and category."""
    sql = "SELECT fiscal_year, category, sum(mentions) AS mentions FROM fct_risk_mentions WHERE 1=1"
    params: list[Any] = []
    if ticker:
        sql += " AND upper(ticker) = upper(?)"
        params.append(ticker)
    if category:
        sql += " AND category = ?"
        params.append(category)
    return gold.query(sql + " GROUP BY 1, 2 ORDER BY 1, 2", params)


@mcp.tool()
def get_section_text(accession_no: str, item: str, max_chars: int = 8000) -> dict[str, Any]:
    """Full text of one 10-K item (e.g. '1A' risk factors, '7' MD&A) of one filing."""
    text, title = load_section_text(accession_no, item.upper())
    return {
        "accession_no": accession_no,
        "item": item.upper(),
        "title": title,
        "text": text[:max_chars],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
