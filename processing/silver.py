"""Silver text layer: bronze document -> sectioned plain text (Parquet + per-section text objects)."""

from __future__ import annotations

from datetime import UTC, datetime

import pyarrow as pa
from sqlalchemy import delete, select

from core import storage
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import Filing, Quarantine, Section
from core.telemetry import pipeline_run, tracer
from processing.parse import document_to_text
from processing.sectioning import KEEP, SCHEMA_VERSION, SectionText, split_items

log = get_logger(__name__)

SECTIONS_SCHEMA = pa.schema(
    [
        ("accession_no", pa.string()),
        ("cik", pa.int64()),
        ("item", pa.string()),
        ("title", pa.string()),
        ("text", pa.large_string()),
        ("char_count", pa.int32()),
        ("token_estimate", pa.int32()),
        ("schema_version", pa.string()),
        ("parsed_at", pa.timestamp("us", tz="UTC")),
    ]
)


class NoSectionsError(ValueError):
    pass


def section_text_key(cik: int, accession_no: str, item: str) -> str:
    return f"sections/v{SCHEMA_VERSION}/{cik}/{accession_no}/item_{item}.txt"


def sections_parquet_key(cik: int, accession_no: str) -> str:
    return f"sections/v{SCHEMA_VERSION}/parquet/cik={cik}/{accession_no}.parquet"


def sections_table(cik: int, accession_no: str, sections: list[SectionText]) -> pa.Table:
    now = datetime.now(UTC)
    return pa.Table.from_pylist(
        [
            {
                "accession_no": accession_no,
                "cik": cik,
                "item": s.item,
                "title": s.title,
                "text": s.text,
                "char_count": len(s.text),
                "token_estimate": s.token_estimate,
                "schema_version": SCHEMA_VERSION,
                "parsed_at": now,
            }
            for s in sections
        ],
        schema=SECTIONS_SCHEMA,
    )


def quarantine(accession_no: str, stage: str, error: str, payload_key: str | None = None) -> None:
    with session_scope() as s:
        s.add(
            Quarantine(
                accession_no=accession_no, stage=stage, error=error[:4000], payload_key=payload_key
            )
        )
        filing = s.get(Filing, accession_no)
        if filing is not None:
            filing.status = "quarantined"


def parse_filing(accession_no: str) -> int:
    """Parse one bronze filing into silver sections. Returns the number of sections written."""
    s3 = get_settings()
    with session_scope() as s:
        filing = s.get(Filing, accession_no)
        if filing is None or not filing.bronze_key:
            raise ValueError(f"filing {accession_no} is not in bronze")
        cik, key = filing.cik, filing.bronze_key
    with tracer(__name__).start_as_current_span("parse_filing") as span:
        span.set_attribute("docflow.accession_no", accession_no)
        raw = storage.get_bytes(s3.bronze_bucket, key)
        text = document_to_text(key, raw)
        sections = split_items(text, KEEP)
        if not any(sec.item in ("1A", "7", "8") for sec in sections):
            raise NoSectionsError("no Item 1A/7/8 headings found")
        for sec in sections:
            storage.put_bytes(
                s3.silver_bucket,
                section_text_key(cik, accession_no, sec.item),
                sec.text.encode("utf-8"),
                "text/plain; charset=utf-8",
            )
        storage.put_parquet(
            s3.silver_bucket,
            sections_parquet_key(cik, accession_no),
            sections_table(cik, accession_no, sections),
        )
        with session_scope() as s:
            s.execute(delete(Section).where(Section.accession_no == accession_no))
            for sec in sections:
                s.add(
                    Section(
                        accession_no=accession_no,
                        item=sec.item,
                        title=sec.title,
                        text_key=section_text_key(cik, accession_no, sec.item),
                        char_count=len(sec.text),
                        token_estimate=sec.token_estimate,
                        schema_version=SCHEMA_VERSION,
                    )
                )
            filing_row = s.get(Filing, accession_no)
            if filing_row is not None and filing_row.status in ("ingested", "quarantined"):
                filing_row.status = "parsed"
        span.set_attribute("docflow.sections", len(sections))
        return len(sections)


def parse_pending(
    limit: int | None = None, reparse: bool = False, run_id: str | None = None
) -> dict[str, int]:
    with session_scope() as s:
        q = (
            select(Filing.accession_no)
            .where(Filing.form_type != "INVOICE")
            .order_by(Filing.filed_at.desc())
        )
        if not reparse:
            q = q.where(Filing.status == "ingested")
        if limit:
            q = q.limit(limit)
        accessions = list(s.scalars(q))
    ok = failed = 0
    with pipeline_run("parse_and_section", run_id) as run:
        run.docs_in = len(accessions)
        for acc in accessions:
            try:
                parse_filing(acc)
                ok += 1
            except Exception as exc:
                failed += 1
                log.warning("parse.failed", accession=acc, error=str(exc))
                quarantine(acc, "parse", f"{type(exc).__name__}: {exc}")
        run.docs_ok, run.docs_quarantined = ok, failed
    log.info("parse.done", ok=ok, failed=failed)
    return {"parsed": ok, "quarantined": failed}


def load_section_text(accession_no: str, item: str) -> tuple[str, str | None]:
    """Returns (text, title) for a stored section."""
    with session_scope() as s:
        sec = s.scalar(
            select(Section).where(Section.accession_no == accession_no, Section.item == item)
        )
        if sec is None:
            raise KeyError(f"{accession_no} item {item}")
        key, title = sec.text_key, sec.title
    return storage.get_bytes(get_settings().silver_bucket, key).decode("utf-8"), title
