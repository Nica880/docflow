"""Bronze layer: raw filings exactly as downloaded + the `filings` manifest.

Idempotent by construction: the object key is derived from (CIK, accession number) and a filing
whose manifest row already has a checksum *and* whose object exists is skipped without a download.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

from core import storage
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import Company, Filing, Quarantine
from core.telemetry import pipeline_run
from ingestion.edgar import CompanyInfo, EdgarClient, FilingRef
from ingestion.sectors import sector_for_sic

log = get_logger(__name__)

Outcome = Literal["new", "skipped", "failed"]


def bronze_key(ref: FilingRef) -> str:
    return f"{ref.cik}/{ref.accession_no}/{ref.primary_document}"


def companyfacts_key(cik: int) -> str:
    return f"{cik}/companyfacts.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upsert_company(info: CompanyInfo) -> None:
    with session_scope() as s:
        s.merge(
            Company(
                cik=info.cik,
                name=info.name,
                ticker=info.ticker,
                sic_code=info.sic_code,
                sector=sector_for_sic(info.sic_code),
            )
        )


class BronzeWriter:
    def __init__(self, client: EdgarClient, run_id: str | None = None) -> None:
        self.client = client
        self.run_id = run_id
        self.bucket = get_settings().bronze_bucket

    def already_ingested(self, ref: FilingRef) -> bool:
        with session_scope() as s:
            row = s.get(Filing, ref.accession_no)
            if row is None or not row.checksum or not row.bronze_key:
                return False
            key = row.bronze_key
        return storage.exists(self.bucket, key)

    def ingest(self, ref: FilingRef) -> Outcome:
        if self.already_ingested(ref):
            return "skipped"
        try:
            data = self.client.download(ref.document_url)
        except Exception as exc:
            log.warning("bronze.download_failed", accession=ref.accession_no, error=str(exc))
            with session_scope() as s:
                s.add(Quarantine(accession_no=ref.accession_no, stage="ingest", error=str(exc)))
            return "failed"
        key = bronze_key(ref)
        checksum = sha256(data)
        ctype = "application/pdf" if key.lower().endswith(".pdf") else "text/html"
        storage.put_bytes(self.bucket, key, data, ctype)
        meta = {
            "cik": ref.cik,
            "accession_no": ref.accession_no,
            "form_type": ref.form_type,
            "filed_at": ref.filed_at.isoformat(),
            "source_url": ref.document_url,
            "checksum": checksum,
            "ingest_run_id": self.run_id,
            "downloaded_at": datetime.now(UTC).isoformat(),
        }
        storage.put_bytes(
            self.bucket, key + ".meta.json", json.dumps(meta).encode(), "application/json"
        )
        with session_scope() as s:
            existing = s.get(Filing, ref.accession_no)
            status = existing.status if existing and existing.checksum == checksum else "ingested"
            s.merge(
                Filing(
                    accession_no=ref.accession_no,
                    cik=ref.cik,
                    form_type=ref.form_type,
                    filed_at=ref.filed_at,
                    period_end=ref.period_end,
                    source_url=ref.document_url,
                    checksum=checksum,
                    bronze_key=key,
                    size_bytes=len(data),
                    ingest_run_id=self.run_id,
                    status=status,
                )
            )
        return "new"

    def ingest_companyfacts(self, cik: int) -> bool:
        """XBRL company facts: used as ground truth for financial figures."""
        try:
            facts = self.client.company_facts(cik)
        except Exception as exc:
            log.info("bronze.companyfacts_unavailable", cik=cik, error=str(exc))
            return False
        storage.put_bytes(
            self.bucket, companyfacts_key(cik), json.dumps(facts).encode(), "application/json"
        )
        return True


@dataclass
class IngestResult:
    run_id: str
    companies: int = 0
    new: int = 0
    skipped: int = 0
    failed: int = 0
    accessions: list[str] = field(default_factory=list)


def ingest_tickers(
    tickers: Iterable[str],
    forms: tuple[str, ...] = ("10-K",),
    since: date | None = None,
    until: date | None = None,
    max_per_company: int | None = None,
    max_filings: int | None = None,
    max_workers: int = 4,
    dag_id: str = "edgar_ingest",
    run_id: str | None = None,
) -> IngestResult:
    """Ingest filings for a list of tickers into bronze. Parallel by filing, globally rate limited."""
    storage.ensure_buckets()
    client = EdgarClient()
    try:
        ticker_map = client.company_tickers()
        ciks = []
        for t in tickers:
            cik = ticker_map.get(t.upper())
            if cik is None:
                log.warning("ingest.unknown_ticker", ticker=t)
            else:
                ciks.append(cik)
        return ingest_ciks(
            client,
            ciks,
            forms,
            since,
            until,
            max_per_company,
            max_filings,
            max_workers,
            dag_id,
            run_id,
        )
    finally:
        client.close()


def ingest_ciks(
    client: EdgarClient,
    ciks: list[int],
    forms: tuple[str, ...],
    since: date | None,
    until: date | None,
    max_per_company: int | None,
    max_filings: int | None,
    max_workers: int,
    dag_id: str,
    run_id: str | None,
) -> IngestResult:
    with pipeline_run(dag_id, run_id) as run:
        result = IngestResult(run_id=run.run_id)
        writer = BronzeWriter(client, run.run_id)
        refs: list[FilingRef] = []
        for cik in ciks:
            try:
                info, company_refs = client.list_filings(cik, forms, since, until)
            except Exception as exc:
                log.warning("ingest.list_failed", cik=cik, error=str(exc))
                continue
            upsert_company(info)
            writer.ingest_companyfacts(cik)
            result.companies += 1
            refs.extend(company_refs[:max_per_company] if max_per_company else company_refs)
        if max_filings:
            refs = refs[:max_filings]
        run.docs_in = len(refs)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(writer.ingest, ref): ref for ref in refs}
            for fut in as_completed(futures):
                outcome = fut.result()
                ref = futures[fut]
                if outcome == "new":
                    result.new += 1
                    result.accessions.append(ref.accession_no)
                elif outcome == "skipped":
                    result.skipped += 1
                else:
                    result.failed += 1
        run.docs_ok = result.new + result.skipped
        run.docs_quarantined = result.failed
        log.info(
            "ingest.done",
            run_id=run.run_id,
            companies=result.companies,
            new=result.new,
            skipped=result.skipped,
            failed=result.failed,
        )
        return result
