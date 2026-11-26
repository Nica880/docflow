# MCP server

DocFlow exposes its warehouse and filings through the [Model Context Protocol](https://modelcontextprotocol.io)
so any MCP client (Claude Desktop, IDE agents, other agents) can use them as tools.

| Tool | What it does |
|---|---|
| `search_filings(query, ticker?, limit?)` | Semantic search over 10-K sections (pgvector) |
| `get_company_financials(ticker)` | Revenue / net income / operating cash flow by fiscal year, LLM vs. XBRL |
| `get_risk_trends(ticker?, category?)` | Risk-factor mentions per year and category |
| `get_section_text(accession_no, item, max_chars?)` | Raw text of one 10-K item |

Run it on stdio (the stack from `make up` must be running and `make demo` must have built gold):

```bash
uv run docflow mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "docflow": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/docflow", "docflow", "mcp"],
      "env": {
        "DATABASE_URL": "postgresql+psycopg://docflow:docflow@localhost:5432/docflow",
        "S3_ENDPOINT_URL": "http://localhost:9000"
      }
    }
  }
}
```
