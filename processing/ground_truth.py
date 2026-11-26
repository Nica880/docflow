"""Ground truth for financial figures from XBRL company facts (machine-readable, filed by the
company itself), complemented by reviewer corrections (`source='review'`)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select

from core import storage
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import Filing, GroundTruth
from ingestion.bronze import companyfacts_key

log = get_logger(__name__)

CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenuesNetOfInterestExpense",
    ),
    "net_income": ("NetIncomeLoss",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
}


def _annual(fact: dict[str, Any], period_end: date | None) -> bool:
    if fact.get("form") != "10-K" or "start" not in fact:
        return False
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    if not 350 <= days <= 380:
        return False
    return period_end is None or fact["end"] == period_end.isoformat()


def facts_for_filing(
    companyfacts: dict[str, Any], accession_no: str, period_end: date | None
) -> dict[str, float]:
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    out: dict[str, float] = {}
    for field, concepts in CONCEPTS.items():
        for concept in concepts:
            units = gaap.get(concept, {}).get("units", {}).get("USD", [])
            hits = [f for f in units if f.get("accn") == accession_no and _annual(f, period_end)]
            if hits:
                out[field] = float(hits[0]["val"])
                break
    return out


def xbrl_facts_rows(companyfacts: dict[str, Any], cik: int) -> list[dict[str, Any]]:
    """Flatten annual 10-K facts for the warehouse (`stg_xbrl_facts`)."""
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    rows = []
    for field, concepts in CONCEPTS.items():
        for concept in concepts:
            for f in gaap.get(concept, {}).get("units", {}).get("USD", []):
                if _annual(f, None):
                    rows.append(
                        {
                            "cik": cik,
                            "field": field,
                            "concept": concept,
                            "accession_no": f.get("accn"),
                            "period_start": f["start"],
                            "period_end": f["end"],
                            "fiscal_year": int(f["end"][:4]),
                            "value": float(f["val"]),
                            "filed": f.get("filed"),
                        }
                    )
    return rows


def load_companyfacts(cik: int) -> dict[str, Any] | None:
    s = get_settings()
    key = companyfacts_key(cik)
    if not storage.exists(s.bronze_bucket, key):
        return None
    return json.loads(storage.get_bytes(s.bronze_bucket, key))


def seed_ground_truth() -> int:
    with session_scope() as s:
        filings = s.execute(
            select(Filing.accession_no, Filing.cik, Filing.period_end).where(
                Filing.form_type == "10-K"
            )
        ).all()
    cache: dict[int, dict[str, Any] | None] = {}
    written = 0
    for acc, cik, period_end in filings:
        if cik not in cache:
            cache[cik] = load_companyfacts(cik)
        facts = cache[cik]
        if not facts:
            continue
        values = facts_for_filing(facts, acc, period_end)
        if period_end:
            values_year = {"fiscal_year": float(period_end.year)}
            values = values | values_year if values else values
        with session_scope() as s:
            for field, value in values.items():
                existing = s.scalar(
                    select(GroundTruth).where(
                        GroundTruth.accession_no == acc,
                        GroundTruth.field == field,
                        GroundTruth.source == "xbrl",
                    )
                )
                if existing is None:
                    s.add(
                        GroundTruth(accession_no=acc, field=field, value=repr(value), source="xbrl")
                    )
                    written += 1
                else:
                    existing.value = repr(value)
    log.info("ground_truth.seeded", rows=written)
    return written
