from __future__ import annotations

import time
from datetime import date

import httpx
import pytest

from ingestion.edgar import EdgarClient, EdgarConfigError, parse_filing_blocks
from ingestion.ratelimit import RateLimiter
from ingestion.sectors import sector_for_sic
from tests.conftest import FIXTURES


def test_rate_limiter_enforces_rate() -> None:
    limiter = RateLimiter(rate_per_s=50)
    t0 = time.monotonic()
    for _ in range(6):
        limiter.acquire()
    # first token is free, the next 5 need >= 5/50 s
    assert time.monotonic() - t0 >= 0.09


def test_user_agent_requires_email() -> None:
    with pytest.raises(EdgarConfigError):
        EdgarClient(user_agent="no contact here")


def test_parse_filing_blocks_filters_dedupes_and_sorts() -> None:
    block = {
        "accessionNumber": ["a-1", "a-2", "a-3", "a-1", "a-4"],
        "form": ["10-K", "10-Q", "10-K", "10-K", "10-K"],
        "filingDate": ["2020-02-01", "2021-05-01", "2023-02-01", "2020-02-01", "2015-02-01"],
        "reportDate": ["2019-12-31", "", "2022-12-31", "2019-12-31", ""],
        "primaryDocument": ["x.htm", "q.htm", "y.htm", "x.htm", "old.htm"],
    }
    refs = parse_filing_blocks(1, [block], ("10-K",), date(2016, 1, 1), None)
    assert [r.accession_no for r in refs] == ["a-3", "a-1"]
    assert refs[0].period_end == date(2022, 12, 31)
    assert refs[0].document_url.endswith("/1/a3/y.htm")


def test_offline_fixture_transport_lists_real_filings() -> None:
    from ingestion.fixtures import FixtureTransport

    client = EdgarClient(transport=FixtureTransport(FIXTURES))
    tickers = client.company_tickers()
    info, refs = client.list_filings(tickers["AAPL"], include_older_pages=False)
    assert info.name.startswith("Apple")
    assert len(refs) == 2 and all(r.form_type == "10-K" for r in refs)
    assert b"Apple" in client.download(refs[0].document_url)


def test_retries_transient_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503 if calls["n"] == 1 else 200, json={"ok": True})

    client = EdgarClient(transport=httpx.MockTransport(handler), max_rps=100)
    assert client.get_json("https://data.sec.gov/x.json") == {"ok": True}
    assert calls["n"] == 2


@pytest.mark.parametrize(
    ("sic", "sector"),
    [
        ("3674", "Semiconductors"),
        ("7372", "Software & Internet"),
        ("6021", "Banks"),
        (None, None),
        ("abc", None),
    ],
)
def test_sector_mapping(sic: str | None, sector: str | None) -> None:
    assert sector_for_sic(sic) == sector
