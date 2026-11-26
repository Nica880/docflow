from __future__ import annotations

from processing.extract import score_invoice
from processing.invoices import make_invoice
from processing.llm import RulesProvider
from processing.parse import pdf_to_text
from processing.schemas import Invoice, json_schema


def _extract(seed: int) -> tuple[Invoice, str]:
    _, pdf, _ = make_invoice(seed)
    text = pdf_to_text(pdf)
    out = RulesProvider().complete_json(
        "", [{"role": "user", "content": text}], json_schema("Invoice")
    )
    return Invoice.model_validate_json(out.content), text


def test_clean_invoice_passes_cross_checks() -> None:
    inv, text = _extract(1)
    assert inv.invoice_number == "INV-2026-0001" and inv.line_items
    assert all(s.score >= 0.7 for s in score_invoice(inv, text).values())


def test_invoice_with_injected_error_goes_to_review() -> None:
    inv, text = _extract(3)  # every third invoice has a wrong total on purpose
    assert score_invoice(inv, text)["total"].score < 0.7
