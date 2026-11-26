"""Synthetic invoices (fully made-up vendors) for the human-review demo.

Some invoices are generated with deliberate inconsistencies (wrong total, VAT mismatch) so the
confidence cross-checks route them to the review queue.
"""

from __future__ import annotations

import io
import random
from datetime import date, timedelta

from core import storage
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import Company, Filing
from processing.extract import Outcome, extract_and_store
from processing.llm import get_provider
from processing.parse import pdf_to_text

log = get_logger(__name__)

INVOICE_CIK = 0
VENDORS = [
    "Northwind Office Supply GmbH",
    "Blue Fjord Logistics AS",
    "Atlas Cloud Hosting SRL",
    "Pinecone Print & Design Ltd",
    "Helios Energy Services SA",
]
PRODUCTS = [
    ("Ergonomic office chair", 189.00),
    ("Cloud VM (monthly)", 74.50),
    ("Freight Bucharest-Oslo", 1250.00),
    ("Brochure printing (500 pcs)", 340.00),
    ("Consulting hour", 120.00),
    ("Electricity audit", 900.00),
    ("Laptop docking station", 215.90),
]


def make_invoice(seed: int) -> tuple[str, bytes, str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    rnd = random.Random(seed)  # noqa: S311 - synthetic demo data
    number = f"INV-2026-{seed:04d}"
    vendor = rnd.choice(VENDORS)
    issued = date(2026, 1, 1) + timedelta(days=rnd.randint(0, 300))
    items = []
    for desc, price in rnd.sample(PRODUCTS, rnd.randint(2, 4)):
        qty = rnd.randint(1, 5)
        items.append((desc, qty, price, round(qty * price, 2)))
    subtotal = round(sum(i[3] for i in items), 2)
    rate = rnd.choice([0.19, 0.21, 0.25])
    vat = round(subtotal * rate, 2)
    total = round(subtotal + vat, 2)
    if seed % 3 == 0:  # deliberate error -> should land in the review queue
        total = round(total + rnd.choice([10, 100, 0.5]), 2)

    lines = [
        "INVOICE",
        f"Vendor: {vendor}",
        f"Invoice number: {number}",
        f"Invoice date: {issued.isoformat()}",
        f"Due date: {(issued + timedelta(days=30)).isoformat()}",
        "Currency: EUR",
        "",
        *[f"{d} {q} x {p:,.2f} = {a:,.2f}" for d, q, p, a in items],
        "",
        f"Subtotal: {subtotal:,.2f}",
        f"VAT rate: {rate * 100:.0f}%",
        f"VAT amount: {vat:,.2f}",
        f"Total: {total:,.2f}",
    ]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 18
    c.showPage()
    c.save()
    return number, buf.getvalue(), issued.isoformat()


def generate_and_extract(n: int = 6, model: str | None = None) -> list[Outcome]:
    s = get_settings()
    storage.ensure_buckets()
    provider = get_provider(model)
    with session_scope() as sess:
        sess.merge(
            Company(cik=INVOICE_CIK, name="Synthetic invoices (demo)", ticker=None, sector="Demo")
        )
    outcomes = []
    for seed in range(1, n + 1):
        number, pdf, issued = make_invoice(seed)
        key = f"invoices/{number}.pdf"
        storage.put_bytes(s.bronze_bucket, key, pdf, "application/pdf")
        with session_scope() as sess:
            sess.merge(
                Filing(
                    accession_no=number,
                    cik=INVOICE_CIK,
                    form_type="INVOICE",
                    filed_at=date.fromisoformat(issued),
                    source_url=f"s3://{s.bronze_bucket}/{key}",
                    bronze_key=key,
                    size_bytes=len(pdf),
                    status="extracted",
                )
            )
        text = pdf_to_text(pdf)
        outcomes.append(
            extract_and_store(number, "Invoice", text, None, provider, s.prompt_version)
        )
    log.info("invoices.done", n=n, reviews=sum(o.review_tasks for o in outcomes))
    return outcomes
