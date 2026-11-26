from __future__ import annotations

import gzip
import json

import pytest

from api.agent.agent import detect_ticker, in_domain
from api.agent.sql_guard import UnsafeSQL, validate_sql
from api.routers.filings import locate
from processing.evaluation import Accumulator, score_doc, threshold_analysis, values_match
from processing.extract import Outcome
from processing.ground_truth import facts_for_filing
from tests.conftest import FIXTURES

COMPANIES = [("Apple Inc.", "AAPL", "320193"), ("NVIDIA CORP", "NVDA", "1045810")]


@pytest.mark.parametrize(
    "sql",
    [
        "select * from fct_financials",
        "with t as (select * from dim_company) select name from t",
        "select ticker, sum(mentions) from fct_risk_mentions group by 1 order by 2 desc limit 10",
    ],
)
def test_sql_guard_allows_reads_and_caps_rows(sql: str) -> None:
    assert "LIMIT" in validate_sql(sql, row_limit=50)


@pytest.mark.parametrize(
    "sql",
    [
        "drop table dim_company",
        "select 1; select 2",
        "select * from filings",
        "select * from main.dim_company",
        "select * from read_csv('/etc/passwd')",
        "select * from 'data/lake/companies/part-0.parquet'",
        "select read_text('secrets')",
        "select getenv('HOME')",
        "copy dim_company to 'out.csv'",
        "attach 'other.db'",
    ],
)
def test_sql_guard_blocks_unsafe(sql: str) -> None:
    with pytest.raises(UnsafeSQL):
        validate_sql(sql)


def test_sql_guard_overrides_large_limits() -> None:
    assert validate_sql("select * from dim_company limit 100000", row_limit=10).endswith("LIMIT 10")


def test_agent_domain_check_refuses_off_topic() -> None:
    assert not in_domain("What is the weather in Paris?", COMPANIES)
    assert not in_domain("Write me a poem about the sea", COMPANIES)
    assert in_domain("How did cybersecurity risk change?", COMPANIES)
    assert in_domain("Tell me about Nvidia", COMPANIES)
    assert detect_ticker("what does apple say about suppliers", COMPANIES) == "AAPL"


def test_xbrl_ground_truth_for_apple() -> None:
    path = next(FIXTURES.rglob("CIK0000320193.json.gz"))
    facts = json.loads(gzip.decompress(path.read_bytes()))
    from datetime import date

    gt = facts_for_filing(facts, "0000320193-25-000079", date(2025, 9, 27))
    assert gt["revenue"] == 416_161_000_000
    assert gt["net_income"] == 112_010_000_000


def test_eval_scoring_and_threshold_analysis() -> None:
    assert (
        values_match(100.0, 100.4) and not values_match(100.0, 101.0) and not values_match(1, None)
    )
    acc = Accumulator()
    outcome = Outcome(
        "FinancialHighlights",
        ok=True,
        latency_ms=1200,
        payload={"units": "millions", "fiscal_year": 2025, "revenue": 416161, "net_income": 1.0},
        confidence={"revenue": {"score": 0.9}, "net_income": {"score": 0.4}},
    )
    score_doc(
        acc,
        [outcome],
        {"revenue": "416161000000.0", "net_income": "112010000000.0", "fiscal_year": "2025.0"},
    )
    m = acc.metrics()
    assert m["field_accuracy"] == {"revenue": 1.0, "net_income": 0.0, "fiscal_year": 1.0}
    assert m["docs_per_hour"] == 3000.0
    # at 0.7 only the (correct) revenue field is auto-accepted
    assert threshold_analysis(acc.calibration)["0.7"] == {
        "auto_accept_rate": 0.5,
        "auto_accept_precision": 1.0,
    }


def test_highlight_locate_tolerates_whitespace() -> None:
    text = "Revenue grew.\nTotal net   sales\n$ 416,161 in 2025."
    start, end = locate(text, "Total net sales $ 416,161") or (0, 0)
    assert text[start:end].startswith("Total net") and text[start:end].endswith("416,161")
