"""SEC EDGAR client: company tickers, submissions, filing documents, XBRL company facts.

Fair-access rules (https://www.sec.gov/os/accessing-edgar-data): descriptive User-Agent with a
contact email and at most 10 requests/second across all threads. Every request goes through one
shared `RateLimiter`; 429/5xx are retried with exponential backoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import get_settings
from core.logging import get_logger
from ingestion.ratelimit import RateLimiter

log = get_logger(__name__)


class EdgarConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class FilingRef:
    cik: int
    accession_no: str
    form_type: str
    filed_at: date
    period_end: date | None
    primary_document: str

    @property
    def folder_url(self) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{self.cik}/{self.accession_no.replace('-', '')}"

    @property
    def document_url(self) -> str:
        return f"{self.folder_url}/{self.primary_document}"


@dataclass(frozen=True)
class CompanyInfo:
    cik: int
    name: str
    ticker: str | None
    sic_code: str | None
    sic_description: str | None


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (403, 429, 500, 502, 503, 504)
    return isinstance(exc, httpx.TransportError)


class EdgarClient:
    def __init__(
        self,
        user_agent: str | None = None,
        max_rps: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        s = get_settings()
        ua = user_agent if user_agent is not None else s.sec_user_agent
        if "@" not in ua:
            raise EdgarConfigError(
                "SEC_USER_AGENT must include a contact email, e.g. 'DocFlow research you@example.com'"
            )
        self.limiter = RateLimiter(max_rps or s.sec_max_rps)
        if transport is None and s.edgar_fixtures_dir is not None:
            from ingestion.fixtures import FixtureTransport

            transport = FixtureTransport(s.edgar_fixtures_dir)
        self.http = httpx.Client(
            headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(self, url: str) -> httpx.Response:
        self.limiter.acquire()
        resp = self.http.get(url)
        if resp.status_code >= 400:
            log.warning("edgar.http_error", url=url, status=resp.status_code)
        resp.raise_for_status()
        return resp

    def get_json(self, url: str) -> Any:
        return self.get(url).json()

    # --- endpoints ------------------------------------------------------------------------

    def company_tickers(self) -> dict[str, int]:
        """ticker -> CIK."""
        data = self.get_json("https://www.sec.gov/files/company_tickers.json")
        return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}

    def submissions(self, cik: int) -> dict[str, Any]:
        return self.get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")

    def company_facts(self, cik: int) -> dict[str, Any]:
        return self.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")

    def download(self, url: str) -> bytes:
        return self.get(url).content

    def list_filings(
        self,
        cik: int,
        forms: tuple[str, ...] = ("10-K",),
        since: date | None = None,
        until: date | None = None,
        include_older_pages: bool = True,
    ) -> tuple[CompanyInfo, list[FilingRef]]:
        sub = self.submissions(cik)
        info = CompanyInfo(
            cik=cik,
            name=sub.get("name", ""),
            ticker=(sub.get("tickers") or [None])[0],
            sic_code=str(sub.get("sic") or "") or None,
            sic_description=sub.get("sicDescription"),
        )
        blocks = [sub["filings"]["recent"]]
        if include_older_pages:
            for page in sub["filings"].get("files", []):
                # Older pages only matter if we look further back than "recent" covers.
                if since is None or page.get("filingTo", "9999") >= since.isoformat():
                    blocks.append(self.get_json(f"https://data.sec.gov/submissions/{page['name']}"))
        refs = parse_filing_blocks(cik, blocks, forms, since, until)
        return info, refs


def parse_filing_blocks(
    cik: int,
    blocks: list[dict[str, list[Any]]],
    forms: tuple[str, ...],
    since: date | None,
    until: date | None,
) -> list[FilingRef]:
    seen: set[str] = set()
    refs: list[FilingRef] = []
    for block in blocks:
        for i, acc in enumerate(block.get("accessionNumber", [])):
            form = block["form"][i]
            if form not in forms or acc in seen:
                continue
            filed = date.fromisoformat(block["filingDate"][i])
            if (since and filed < since) or (until and filed > until):
                continue
            doc = block["primaryDocument"][i]
            if not doc:
                continue
            report = block.get("reportDate", [""] * (i + 1))[i]
            seen.add(acc)
            refs.append(
                FilingRef(
                    cik=cik,
                    accession_no=acc,
                    form_type=form,
                    filed_at=filed,
                    period_end=date.fromisoformat(report) if report else None,
                    primary_document=doc,
                )
            )
    refs.sort(key=lambda r: r.filed_at, reverse=True)
    return refs
