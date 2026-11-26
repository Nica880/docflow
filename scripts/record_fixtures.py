"""Record a small, trimmed set of real EDGAR responses for offline tests / CI / demo.

    uv run python scripts/record_fixtures.py --tickers AAPL MSFT NVDA JPM GS --per-company 2

Documents are minimized (inline-XBRL header and inline styles removed) and gzipped, JSON is
trimmed to what the pipeline reads. Respects the SEC fair-access policy via EdgarClient.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path
from typing import Any

from ingestion.edgar import EdgarClient
from ingestion.fixtures import fixture_path

XBRL_CONCEPTS = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
}


def minimize_html(html: str) -> str:
    html = re.sub(r"(?is)<ix:header>.*?</ix:header>", "", html)
    html = re.sub(
        r'(?i)\s(style|class|id|contextref|unitref|decimals|scale|format|name)="[^"]*"', "", html
    )
    html = re.sub(r"(?is)<img[^>]*>", "", html)
    return re.sub(r"[ \t]+", " ", html)


def write(root: Path, url: str, data: bytes, gz: bool = False) -> None:
    path = fixture_path(root, url)
    if gz:
        path = path.with_name(path.name + ".gz")
        data = gzip.compress(data, compresslevel=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def trim_submissions(sub: dict[str, Any], keep: set[str]) -> dict[str, Any]:
    recent = sub["filings"]["recent"]
    idx = [i for i, acc in enumerate(recent["accessionNumber"]) if acc in keep]
    sub["filings"]["recent"] = {k: [v[i] for i in idx] for k, v in recent.items()}
    sub["filings"]["files"] = []
    return {k: sub[k] for k in ("cik", "name", "tickers", "sic", "sicDescription", "filings")}


def trim_facts(facts: dict[str, Any]) -> dict[str, Any]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    return {
        "cik": facts.get("cik"),
        "entityName": facts.get("entityName"),
        "facts": {"us-gaap": {k: v for k, v in gaap.items() if k in XBRL_CONCEPTS}},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "NVDA", "JPM", "GS"])
    ap.add_argument("--per-company", type=int, default=2)
    ap.add_argument("--out", type=Path, default=Path("tests/fixtures/edgar"))
    args = ap.parse_args()

    client = EdgarClient()
    tickers = client.company_tickers()
    wanted = {t: tickers[t] for t in args.tickers}
    all_tickers = client.get_json("https://www.sec.gov/files/company_tickers.json")
    trimmed = {k: v for k, v in all_tickers.items() if v["ticker"] in wanted}
    write(args.out, "https://www.sec.gov/files/company_tickers.json", json.dumps(trimmed).encode())

    for ticker, cik in wanted.items():
        _, refs = client.list_filings(cik, ("10-K",), include_older_pages=False)
        refs = refs[: args.per_company]
        sub = trim_submissions(client.submissions(cik), {r.accession_no for r in refs})
        write(
            args.out,
            f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
            json.dumps(sub).encode(),
        )
        facts = trim_facts(client.company_facts(cik))
        write(
            args.out,
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            json.dumps(facts).encode(),
            gz=True,
        )
        for ref in refs:
            html = client.download(ref.document_url).decode("utf-8", errors="replace")
            write(args.out, ref.document_url, minimize_html(html).encode(), gz=True)
            print(f"{ticker} {ref.accession_no} {ref.document_url}")
    client.close()


if __name__ == "__main__":
    main()
