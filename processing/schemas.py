"""Extraction schemas (Pydantic v2). Their JSON Schema constrains the LLM output (Ollama `format`)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RiskCategory = Literal[
    "ai_technology", "cyber", "regulatory", "supply_chain", "macro", "competition", "other"
]
RISK_CATEGORIES: tuple[str, ...] = (
    "ai_technology",
    "cyber",
    "regulatory",
    "supply_chain",
    "macro",
    "competition",
    "other",
)
Units = Literal["units", "thousands", "millions", "billions"]
UNIT_MULTIPLIER: dict[str, float] = {
    "units": 1.0,
    "thousands": 1e3,
    "millions": 1e6,
    "billions": 1e9,
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class FinancialHighlights(_Strict):
    """Headline figures for the fiscal year covered by a 10-K, as reported (before scaling)."""

    fiscal_year: int = Field(ge=1990, le=2100)
    currency: str = Field(default="USD", max_length=3)
    units: Units = "millions"
    revenue: float | None = Field(default=None, description="Total revenue / net sales")
    revenue_snippet: str | None = Field(default=None, max_length=400)
    net_income: float | None = None
    net_income_snippet: str | None = Field(default=None, max_length=400)
    operating_cash_flow: float | None = Field(
        default=None, description="Net cash provided by operating activities"
    )
    operating_cash_flow_snippet: str | None = Field(default=None, max_length=400)
    self_confidence: float = Field(default=0.5, ge=0, le=1)

    FIELDS: ClassVar[tuple[str, ...]] = ("revenue", "net_income", "operating_cash_flow")

    def normalized(self, field: str) -> float | None:
        value = getattr(self, field)
        return None if value is None else float(value) * UNIT_MULTIPLIER[self.units]


class Risk(_Strict):
    category: RiskCategory
    summary: str = Field(max_length=300)
    snippet: str = Field(max_length=400)

    @field_validator("category", mode="before")
    @classmethod
    def _norm_category(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip().lower().replace("/", "_").replace(" ", "_").replace("-", "_")
            aliases = {
                "ai": "ai_technology",
                "technology": "ai_technology",
                "cybersecurity": "cyber",
                "supply": "supply_chain",
                "macroeconomic": "macro",
                "regulation": "regulatory",
                "legal": "regulatory",
            }
            v = aliases.get(v, v)
        return v


class RiskFactors(_Strict):
    risks: list[Risk] = Field(max_length=25)
    self_confidence: float = Field(default=0.5, ge=0, le=1)


class Leadership(_Strict):
    ceo: str | None = Field(default=None, max_length=120)
    ceo_snippet: str | None = Field(default=None, max_length=400)
    cfo: str | None = Field(default=None, max_length=120)
    cfo_snippet: str | None = Field(default=None, max_length=400)
    board_size: int | None = Field(default=None, ge=1, le=40)
    self_confidence: float = Field(default=0.5, ge=0, le=1)

    FIELDS: ClassVar[tuple[str, ...]] = ("ceo", "cfo", "board_size")


class LineItem(_Strict):
    description: str = Field(max_length=200)
    quantity: float
    unit_price: float
    amount: float


class Invoice(_Strict):
    """Synthetic invoices only (human-review demo)."""

    vendor: str = Field(max_length=200)
    invoice_number: str = Field(max_length=50)
    invoice_date: date
    due_date: date | None = None
    currency: str = Field(default="EUR", max_length=3)
    line_items: list[LineItem]
    subtotal: float
    vat_rate: float = Field(ge=0, le=0.5)
    vat_amount: float
    total: float
    self_confidence: float = Field(default=0.5, ge=0, le=1)

    FIELDS: ClassVar[tuple[str, ...]] = (
        "vendor",
        "invoice_number",
        "invoice_date",
        "subtotal",
        "vat_amount",
        "total",
    )


SCHEMAS: dict[str, type[_Strict]] = {
    "FinancialHighlights": FinancialHighlights,
    "RiskFactors": RiskFactors,
    "Leadership": Leadership,
    "Invoice": Invoice,
}
# v2: decoding schema is "quote first" (see json_schema); Pydantic validation is unchanged.
SCHEMA_VERSION = "2"
FILING_SCHEMAS = ("FinancialHighlights", "RiskFactors")


def _quote_first(obj: dict[str, Any]) -> dict[str, Any]:
    """Reorder an object schema so each snippet precedes the value it supports, and require all keys.

    Ollama decodes keys in schema order. With `revenue` before `revenue_snippet` and every value
    optional, 7-8B models on long 10-K contexts emit `"revenue": null` and only then quote the
    correct figure in the snippet (eval 2026-11-26: 0% accuracy on money fields for both qwen2.5
    and llama3.1). Quoting first, then copying the number, fixes it. Nullable fields stay
    nullable, so "not stated" is still expressible as an explicit null.
    """
    props: dict[str, Any] = obj.get("properties", {})
    if not props:
        return obj
    order: list[str] = []
    if "snippet" in props:
        order.append("snippet")
    for key in props:
        if key in order:
            continue
        snippet = f"{key}_snippet"
        if snippet in props and snippet not in order:
            order.append(snippet)
        if key not in order:
            order.append(key)
    return {**obj, "properties": {k: props[k] for k in order}, "required": order}


def json_schema(name: str) -> dict[str, Any]:
    """JSON Schema sent to the LLM as the constrained-decoding `format` (quote-first order)."""
    schema = _quote_first(SCHEMAS[name].model_json_schema())
    if "$defs" in schema:
        schema["$defs"] = {k: _quote_first(v) for k, v in schema["$defs"].items()}
    return schema
