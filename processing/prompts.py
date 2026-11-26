"""Versioned prompts. A prompt change = a new version, so evaluations stay comparable."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str  # formatted with {context}


_SYSTEM_V1 = (
    "You extract structured data from SEC filings. Answer with JSON that matches the given "
    "schema exactly. Use only facts stated in the provided text; if a value is not stated, use "
    "null. Every *_snippet / snippet field must be a short verbatim quote from the text that "
    "contains the value. Set self_confidence between 0 and 1."
)

_SYSTEM_V2 = _SYSTEM_V1 + (
    " Numbers: copy them as reported in the table (no scaling), report the scale in `units` "
    "(look for '(in millions)' style captions), use negative numbers for losses or amounts in "
    "parentheses. Use the most recent fiscal year column (usually the first numeric column)."
)

_USER = {
    "FinancialHighlights": (
        "Extract the headline financial figures (total revenue, net income, net cash provided by "
        "operating activities) for the fiscal year of this 10-K.\n\n{context}"
    ),
    "RiskFactors": (
        "List the distinct risk factors disclosed below (max 15). For each give a category "
        "(ai_technology, cyber, regulatory, supply_chain, macro, competition, other), a one-line "
        "summary and a verbatim snippet.\n\n{context}"
    ),
    "Leadership": ("Extract the CEO name, the CFO name and the board size if stated.\n\n{context}"),
    "Invoice": (
        "Extract the invoice header, all line items and the totals from this invoice.\n\n{context}"
    ),
}

PROMPTS: dict[str, dict[str, Prompt]] = {
    "v1": {name: Prompt(_SYSTEM_V1, user) for name, user in _USER.items()},
    "v2": {name: Prompt(_SYSTEM_V2, user) for name, user in _USER.items()},
}


def get_prompt(version: str, schema_name: str) -> Prompt:
    return PROMPTS[version][schema_name]
