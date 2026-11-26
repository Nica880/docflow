"""Q&A agent: tool-calling loop over SQL (gold), semantic search and section text.

Guarantees: answers cite filing + section; questions outside the data are refused (domain
pre-check, plus refusal when no tool produced evidence).
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select

from api.agent.tools import TOOL_SPECS, run_tool
from api.schemas import Answer, Citation, ToolCallOut
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.metrics import AGENT_REQUESTS
from core.models import Company
from processing.llm import OllamaProvider, classify_risk

log = get_logger(__name__)

REFUSAL = (
    "I can only answer questions about the SEC filings, companies and extracted facts in DocFlow, "
    "and I could not find supporting evidence for this one."
)

DOMAIN_WORDS = (
    "revenue", "income", "earnings", "profit", "cash", "sales", "margin", "financial", "fiscal",
    "risk", "filing", "10-k", "annual report", "company", "companies", "sector", "business",
    "supply", "cyber", "regulat", "competition", "competitor", "ai", "artificial intelligence",
    "macro", "inflation", "interest", "debt", "segment", "customer", "employee", "strategy",
    "md&a", "item", "disclos", "growth", "bank", "lending", "semiconductor", "cloud", "extraction",
    "model", "review", "pipeline", "data", "market", "product", "litigation", "tax",
)  # fmt: skip

SYSTEM = (
    "You are DocFlow's analyst assistant. Answer ONLY from tool results over SEC 10-K filings: "
    "use sql_query for numbers/rankings/trends, semantic_search and get_filing_section for "
    "qualitative questions. Cite filings as (accession_no, Item X). If the data does not "
    "contain the answer, or the question is unrelated to the filings, say you cannot answer. "
    "Be concise."
)

METRIC_WORDS = {
    "revenue": ("revenue", "sales", "top line"),
    "net_income": ("net income", "profit", "earnings"),
    "operating_cash_flow": ("cash flow", "operating cash"),
}


def known_companies() -> list[tuple[str, str | None, str]]:
    with session_scope() as s:
        return [
            (c.name, c.ticker, str(c.cik))
            for c in s.scalars(select(Company).where(Company.cik != 0))
        ]


def detect_ticker(question: str, companies: list[tuple[str, str | None, str]]) -> str | None:
    q = question.lower()
    for name, ticker, _ in companies:
        short = re.sub(
            r"[,.]|\b(inc|corp|corporation|co|group|the|& co)\b", "", name.lower()
        ).strip()
        first = short.split()[0] if short else ""
        if ticker and re.search(rf"\b{re.escape(ticker.lower())}\b", q) and len(ticker) > 1:
            return ticker
        if first and len(first) > 2 and re.search(rf"\b{re.escape(first)}\b", q):
            return ticker
    return None


def in_domain(question: str, companies: list[tuple[str, str | None, str]]) -> bool:
    q = f" {question.lower()} "
    if detect_ticker(question, companies):
        return True
    return any(
        re.search(rf"\b{re.escape(w)}" + (r"\b" if len(w) <= 3 else ""), q) for w in DOMAIN_WORDS
    )


def _dedupe(citations: list[Citation]) -> list[Citation]:
    seen, out = set(), []
    for c in citations:
        key = (c.accession_no, c.item)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out[:8]


def _fmt_money(v: Any) -> str:
    if v is None:
        return "n/a"
    v = float(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(v) >= div:
            return f"${v / div:,.1f}{suf}"
    return f"${v:,.0f}"


class Agent:
    def __init__(self) -> None:
        self.settings = get_settings()

    def ask(self, question: str) -> Answer:
        companies = known_companies()
        if not in_domain(question, companies):
            AGENT_REQUESTS.labels(outcome="refused").inc()
            return Answer(answer=REFUSAL, citations=[], tool_calls=[], refused=True)
        if self.settings.llm_provider == "fake":
            answer = self._plan_rules(question, companies)
        else:
            answer = self._loop_llm(question)
        if not answer.citations:
            answer = Answer(
                answer=REFUSAL, citations=[], tool_calls=answer.tool_calls, refused=True
            )
        AGENT_REQUESTS.labels(outcome="refused" if answer.refused else "answered").inc()
        return answer

    # -- LLM tool-calling loop (Ollama) ---------------------------------------------------------
    def _loop_llm(self, question: str) -> Answer:
        provider = OllamaProvider()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ]
        citations: list[Citation] = []
        calls: list[ToolCallOut] = []
        for _ in range(self.settings.agent_max_steps):
            msg = provider.chat_tools(messages, TOOL_SPECS)
            tool_calls = msg.get("tool_calls") or []
            messages.append(msg)
            if not tool_calls:
                return Answer(
                    answer=msg.get("content", "").strip(),
                    citations=_dedupe(citations),
                    tool_calls=calls,
                )
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                output, cites = run_tool(name, args)
                citations += cites
                calls.append(ToolCallOut(tool=name, input=args, output_preview=output[:400]))
                messages.append({"role": "tool", "content": output[:12000], "tool_name": name})
        return Answer(
            answer="I could not finish within the step budget.",
            citations=[],
            tool_calls=calls,
            refused=True,
        )

    # -- deterministic planner (CI / offline) ----------------------------------------------------
    def _plan_rules(self, question: str, companies: list[tuple[str, str | None, str]]) -> Answer:
        q = question.lower()
        ticker = detect_ticker(question, companies)
        metric = next((m for m, words in METRIC_WORDS.items() if any(w in q for w in words)), None)
        calls: list[ToolCallOut] = []

        def call(name: str, args: dict[str, Any]) -> tuple[Any, list[Citation]]:
            out, cites = run_tool(name, args)
            calls.append(ToolCallOut(tool=name, input=args, output_preview=out[:400]))
            try:
                return json.loads(out), cites
            except json.JSONDecodeError:
                return [], cites

        if metric:
            where = f"AND ticker = '{ticker}'" if ticker else ""
            sql = (
                f"SELECT company_name, ticker, fiscal_year, {metric}, accession_no FROM fct_financials "
                f"WHERE source = 'llm' AND {metric} IS NOT NULL {where} "
                "QUALIFY row_number() OVER (PARTITION BY cik ORDER BY fiscal_year DESC) = 1 "
                f"ORDER BY {metric} DESC LIMIT 5"
            )
            rows, cites = call("sql_query", {"sql": sql})
            if rows:
                label = metric.replace("_", " ")
                lines = [
                    f"{i}. {r['company_name']} ({r['ticker']}) - FY{r['fiscal_year']}: {_fmt_money(r[metric])}"
                    for i, r in enumerate(rows, 1)
                ]
                text = f"Latest-fiscal-year {label} from the extracted 10-K figures:\n" + "\n".join(
                    lines
                )
                return Answer(answer=text, citations=_dedupe(cites), tool_calls=calls)

        if "risk" in q and any(
            w in q for w in ("trend", "change", "over time", "increase", "evolve", "grow")
        ):
            category = classify_risk(q.replace("risk", ""))
            cat_filter = f"WHERE category = '{category}'" if category != "other" else ""
            sql = (
                "SELECT fiscal_year, category, sum(mentions) AS mentions, any_value(accession_no) AS accession_no "
                f"FROM fct_risk_mentions {cat_filter} GROUP BY 1, 2 ORDER BY 1, 2"
            )
            rows, cites = call("sql_query", {"sql": sql})
            if rows:
                lines = [
                    f"- FY{r['fiscal_year']} {r['category']}: {r['mentions']} mentions"
                    for r in rows[:20]
                ]
                text = (
                    "Risk-factor mentions by fiscal year (from extracted Item 1A risks):\n"
                    + "\n".join(lines)
                )
                return Answer(answer=text, citations=_dedupe(cites), tool_calls=calls)

        hits, cites = call(
            "semantic_search",
            {"query": question, "ticker": ticker} if ticker else {"query": question},
        )
        if not hits:
            return Answer(answer=REFUSAL, citations=[], tool_calls=calls, refused=True)
        lines = [
            f"- {h['company']} ({h['accession_no']}, Item {h['item']}): {h['text'][:300]}"
            for h in hits[:3]
        ]
        text = "Most relevant passages from the filings:\n" + "\n".join(lines)
        return Answer(answer=text, citations=_dedupe(cites), tool_calls=calls)
