"""Export operational tables + flattened extraction facts to Parquet (the lake read by dbt).

Writes to ``LAKE_DIR/<table>/part-0.parquet`` and mirrors to the silver bucket under ``lake/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select

from core import storage
from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import (
    Company,
    EvalRun,
    Extraction,
    Filing,
    GroundTruth,
    PipelineRun,
    Quarantine,
    ReviewTask,
    Section,
)
from processing.ground_truth import load_companyfacts, xbrl_facts_rows

log = get_logger(__name__)

TS = pa.timestamp("us", tz="UTC")

SCHEMAS: dict[str, pa.Schema] = {
    "companies": pa.schema(
        [
            ("cik", pa.int64()),
            ("name", pa.string()),
            ("ticker", pa.string()),
            ("sic_code", pa.string()),
            ("sector", pa.string()),
        ]
    ),
    "filings": pa.schema(
        [
            ("accession_no", pa.string()),
            ("cik", pa.int64()),
            ("form_type", pa.string()),
            ("filed_at", pa.date32()),
            ("period_end", pa.date32()),
            ("source_url", pa.string()),
            ("checksum", pa.string()),
            ("size_bytes", pa.int64()),
            ("ingest_run_id", pa.string()),
            ("status", pa.string()),
            ("updated_at", TS),
        ]
    ),
    "sections": pa.schema(
        [
            ("id", pa.int64()),
            ("accession_no", pa.string()),
            ("item", pa.string()),
            ("title", pa.string()),
            ("char_count", pa.int64()),
            ("token_estimate", pa.int64()),
            ("schema_version", pa.string()),
        ]
    ),
    "extractions": pa.schema(
        [
            ("id", pa.int64()),
            ("accession_no", pa.string()),
            ("schema_name", pa.string()),
            ("schema_version", pa.string()),
            ("model", pa.string()),
            ("prompt_version", pa.string()),
            ("payload_json", pa.string()),
            ("overall_confidence", pa.float64()),
            ("attempts", pa.int64()),
            ("latency_ms", pa.int64()),
            ("run_tag", pa.string()),
            ("created_at", TS),
        ]
    ),
    "financial_facts": pa.schema(
        [
            ("extraction_id", pa.int64()),
            ("accession_no", pa.string()),
            ("fiscal_year", pa.int64()),
            ("field", pa.string()),
            ("value", pa.float64()),
            ("units", pa.string()),
            ("value_usd", pa.float64()),
            ("snippet", pa.string()),
            ("confidence", pa.float64()),
            ("model", pa.string()),
            ("prompt_version", pa.string()),
            ("run_tag", pa.string()),
        ]
    ),
    "risk_mentions": pa.schema(
        [
            ("extraction_id", pa.int64()),
            ("accession_no", pa.string()),
            ("risk_index", pa.int64()),
            ("category", pa.string()),
            ("summary", pa.string()),
            ("snippet", pa.string()),
            ("confidence", pa.float64()),
            ("model", pa.string()),
            ("prompt_version", pa.string()),
            ("run_tag", pa.string()),
        ]
    ),
    "review_tasks": pa.schema(
        [
            ("id", pa.int64()),
            ("extraction_id", pa.int64()),
            ("field", pa.string()),
            ("value", pa.string()),
            ("confidence", pa.float64()),
            ("status", pa.string()),
            ("reviewer_value", pa.string()),
            ("reviewed_at", TS),
        ]
    ),
    "ground_truth": pa.schema(
        [
            ("accession_no", pa.string()),
            ("field", pa.string()),
            ("value", pa.string()),
            ("source", pa.string()),
        ]
    ),
    "pipeline_runs": pa.schema(
        [
            ("run_id", pa.string()),
            ("dag_id", pa.string()),
            ("started_at", TS),
            ("finished_at", TS),
            ("docs_in", pa.int64()),
            ("docs_ok", pa.int64()),
            ("docs_quarantined", pa.int64()),
            ("status", pa.string()),
        ]
    ),
    "quarantine": pa.schema(
        [
            ("id", pa.int64()),
            ("accession_no", pa.string()),
            ("stage", pa.string()),
            ("error", pa.string()),
            ("created_at", TS),
        ]
    ),
    "xbrl_facts": pa.schema(
        [
            ("cik", pa.int64()),
            ("field", pa.string()),
            ("concept", pa.string()),
            ("accession_no", pa.string()),
            ("period_start", pa.string()),
            ("period_end", pa.string()),
            ("fiscal_year", pa.int64()),
            ("value", pa.float64()),
            ("filed", pa.string()),
        ]
    ),
    "eval_runs": pa.schema(
        [
            ("id", pa.int64()),
            ("model", pa.string()),
            ("prompt_version", pa.string()),
            ("n_docs", pa.int64()),
            ("metrics_json", pa.string()),
            ("created_at", TS),
        ]
    ),
}

_MULT = {"units": 1.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9}


def _row(obj: Any, cols: list[str]) -> dict[str, Any]:
    return {c: getattr(obj, c) for c in cols}


def _conf(confidence: dict[str, Any], key: str) -> float | None:
    v = confidence.get(key)
    return float(v["score"]) if isinstance(v, dict) and "score" in v else None


def flatten_extraction(ext: Extraction) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fin, risks = [], []
    p, c = ext.payload_json, ext.confidence_json
    base = {
        "extraction_id": ext.id,
        "accession_no": ext.accession_no,
        "model": ext.model,
        "prompt_version": ext.prompt_version,
        "run_tag": ext.run_tag,
    }
    if ext.schema_name == "FinancialHighlights":
        mult = _MULT.get(p.get("units", "millions"), 1e6)
        for field in ("revenue", "net_income", "operating_cash_flow"):
            value = p.get(field)
            fin.append(
                base
                | {
                    "fiscal_year": p.get("fiscal_year"),
                    "field": field,
                    "value": value,
                    "units": p.get("units"),
                    "value_usd": None if value is None else float(value) * mult,
                    "snippet": p.get(f"{field}_snippet"),
                    "confidence": _conf(c, field),
                }
            )
    elif ext.schema_name == "RiskFactors":
        for i, r in enumerate(p.get("risks", [])):
            risks.append(
                base
                | {
                    "risk_index": i,
                    "category": r.get("category"),
                    "summary": r.get("summary"),
                    "snippet": r.get("snippet"),
                    "confidence": _conf(c, f"risks[{i}].category"),
                }
            )
    return fin, risks


def collect() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {k: [] for k in SCHEMAS}
    with session_scope() as s:
        for name, model in (
            ("companies", Company),
            ("filings", Filing),
            ("sections", Section),
            ("review_tasks", ReviewTask),
            ("ground_truth", GroundTruth),
            ("pipeline_runs", PipelineRun),
            ("quarantine", Quarantine),
        ):
            cols = SCHEMAS[name].names
            data[name] = [_row(o, cols) for o in s.scalars(select(model))]
        for ext in s.scalars(select(Extraction)):
            data["extractions"].append(
                {
                    **_row(
                        ext,
                        [
                            c
                            for c in SCHEMAS["extractions"].names
                            if c not in ("payload_json", "overall_confidence")
                        ],
                    ),
                    "payload_json": json.dumps(ext.payload_json),
                    "overall_confidence": ext.confidence_json.get("overall"),
                }
            )
            fin, risks = flatten_extraction(ext)
            data["financial_facts"] += fin
            data["risk_mentions"] += risks
        for run in s.scalars(select(EvalRun)):
            data["eval_runs"].append(
                {
                    **_row(run, ["id", "model", "prompt_version", "n_docs", "created_at"]),
                    "metrics_json": json.dumps(run.metrics_json),
                }
            )
        ciks = [c.cik for c in s.scalars(select(Company)) if c.cik != 0]
    for cik in ciks:
        facts = load_companyfacts(cik)
        if facts:
            data["xbrl_facts"] += xbrl_facts_rows(facts, cik)
    return data


def export_lake(lake_dir: Path | None = None, mirror_to_s3: bool = True) -> dict[str, int]:
    s = get_settings()
    root = lake_dir or s.lake_dir
    counts = {}
    for name, rows in collect().items():
        table = pa.Table.from_pylist(rows, schema=SCHEMAS[name])
        out = root / name / "part-0.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, out, compression="zstd")
        if mirror_to_s3:
            try:
                storage.put_parquet(s.silver_bucket, f"lake/{name}/part-0.parquet", table)
            except Exception as exc:
                log.warning("export.s3_mirror_failed", table=name, error=str(exc))
        counts[name] = table.num_rows
    log.info("export.done", **counts)
    return counts
