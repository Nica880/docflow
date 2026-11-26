from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from processing.extract import (
    ExtractionFailed,
    grounded,
    run_llm,
    score_financials,
    score_invoice,
    value_in_snippet,
)
from processing.llm import HashingEmbedder, LLMResult, RulesProvider, classify_risk, find_figure
from processing.schemas import FinancialHighlights, Invoice, Risk, json_schema


class ScriptedProvider:
    model = "scripted"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[list[dict[str, str]]] = []

    def complete_json(
        self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> LLMResult:
        self.calls.append(list(messages))
        return LLMResult(self.outputs[len(self.calls) - 1], 5, self.model)


VALID_FIN = json.dumps(
    {"fiscal_year": 2025, "units": "millions", "revenue": 100.0, "self_confidence": 0.9}
)


def test_repair_loop_feeds_validation_errors_back() -> None:
    provider = ScriptedProvider(['{"fiscal_year": "not a year"}', VALID_FIN])
    raw = run_llm(provider, "FinancialHighlights", "ctx", "v1")
    assert raw.attempts == 2
    assert isinstance(raw.obj, FinancialHighlights)
    assert "invalid" in provider.calls[1][-1]["content"]


def test_gives_up_after_two_repairs() -> None:
    provider = ScriptedProvider(["{}"] * 3)
    with pytest.raises(ExtractionFailed) as exc:
        run_llm(provider, "FinancialHighlights", "ctx", "v1")
    assert exc.value.attempts == 3


def test_confidence_rewards_grounded_values_and_flags_bad_ones() -> None:
    source = "Total net sales 416,161 391,035\nNet income 112,010 93,736\n"
    good = FinancialHighlights(
        fiscal_year=2025,
        revenue=416161,
        revenue_snippet="Total net sales 416,161",
        net_income=112010,
        net_income_snippet="Net income 112,010",
        self_confidence=0.8,
    )
    scores = score_financials(good, source, date(2025, 9, 27))
    assert scores["revenue"].score >= 0.9
    assert scores["operating_cash_flow"].score == 0.0  # missing -> review

    hallucinated = good.model_copy(
        update={"revenue": 999999.0, "revenue_snippet": "Revenue 999,999"}
    )
    bad = score_financials(hallucinated, source, date(2025, 9, 27))["revenue"]
    assert bad.score < 0.7
    assert any("snippet" in r for r in bad.reasons)


def test_grounding_helpers() -> None:
    assert grounded("Net  income 112,010", "net income 112,010 93,736") == 1.0
    assert grounded(None, "x") == 0.0
    assert value_in_snippet(416161.0, "Total net sales $ 416,161")
    assert not value_in_snippet(5.0, "Total 416,161")


def test_invoice_cross_checks_catch_wrong_total() -> None:
    inv = Invoice(
        vendor="V", invoice_number="INV-1", invoice_date=date(2026, 1, 2),
        line_items=[{"description": "a", "quantity": 2, "unit_price": 10, "amount": 20}],
        subtotal=20, vat_rate=0.19, vat_amount=3.8, total=33.8,
    )  # fmt: skip
    scores = score_invoice(inv, "V INV-1 2026-01-02 20.00 3.80 33.80")
    assert scores["total"].score < 0.7 and "subtotal + VAT != total" in scores["total"].reasons
    assert scores["subtotal"].score >= 0.7


def test_rules_provider_extracts_real_apple_financials(aapl_text: str) -> None:
    from processing.context import financial_context, header
    from processing.sectioning import split_items

    sections = {s.item: s.text for s in split_items(aapl_text)}
    ctx = header("Apple", "10-K", date(2025, 9, 27), "8") + financial_context(sections)
    out = RulesProvider().complete_json(
        "", [{"role": "user", "content": ctx}], json_schema("FinancialHighlights")
    )
    fin = FinancialHighlights.model_validate_json(out.content)
    assert (fin.fiscal_year, fin.units, fin.revenue, fin.net_income) == (
        2025,
        "millions",
        416161,
        112010,
    )
    assert fin.normalized("revenue") == 416_161_000_000


def test_rules_risks_ignore_prompt_and_boilerplate() -> None:
    from processing.prompts import get_prompt
    from processing.schemas import RiskFactors

    context = (
        "Company: X\nForm: 10-K\nFiscal period end: 2025-12-31\nSection: Item 1A\n---\n"
        "The following summarizes factors that could have a material adverse effect on us.\n"
        "A cyber attack or data breach could disrupt our operations and harm our reputation.\n"
    )
    prompt = get_prompt("v1", "RiskFactors").user.format(context=context)
    out = RulesProvider().complete_json(
        "", [{"role": "user", "content": prompt}], json_schema("RiskFactors")
    )
    risks = RiskFactors.model_validate_json(out.content).risks
    assert [r.category for r in risks] == ["cyber"]


def test_find_figure_skips_years() -> None:
    assert find_figure("Net income 2025 2024\nNet income $ 1,234 $ 999", "net_income") == (
        1234.0,
        "Net income $ 1,234",
    )


def test_risk_category_aliases_and_classifier() -> None:
    assert Risk(category="Cybersecurity", summary="s", snippet="x").category == "cyber"
    assert classify_risk("A data breach or ransomware attack could disrupt operations") == "cyber"
    assert classify_risk("We depend on single-source suppliers for components") == "supply_chain"


def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    emb = HashingEmbedder(dim=64)
    a, b = emb.embed(["supply chain risk", "supply chain risk"])
    assert a == b
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9
