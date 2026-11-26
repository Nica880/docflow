"""Evaluation harness: run models x prompt versions on the ground-truth set, score, report.

Ground truth: XBRL company facts (financial figures) + reviewer corrections + optional hand
labels for risk categories (`ground_truth.field = 'risk_categories'`, JSON list).
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import EvalRun, GroundTruth
from processing.extract import extract_filing

log = get_logger(__name__)

FIN_FIELDS = ("revenue", "net_income", "operating_cash_flow")
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
_MULT = {"units": 1.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9}


def values_match(truth: float, pred: float | None, tol: float = 0.005) -> bool:
    if pred is None:
        return False
    if truth == 0:
        return abs(pred) < 1
    return abs(pred - truth) / abs(truth) <= tol


def load_ground_truth(limit: int | None = None) -> dict[str, dict[str, str]]:
    """accession -> field -> value. Review corrections override XBRL; hand labels override both."""
    rank = {"xbrl": 0, "review": 1, "hand": 2}
    gt: dict[str, dict[str, tuple[int, str]]] = defaultdict(dict)
    with session_scope() as s:
        for row in s.scalars(select(GroundTruth)):
            r = rank.get(row.source, 0)
            cur = gt[row.accession_no].get(row.field)
            if cur is None or r >= cur[0]:
                gt[row.accession_no][row.field] = (r, row.value)
    out = {acc: {f: v for f, (_, v) in fields.items()} for acc, fields in gt.items()}
    accs = sorted(out)[:limit] if limit else sorted(out)
    return {a: out[a] for a in accs}


@dataclass
class Accumulator:
    docs: int = 0
    schema_ok: int = 0
    schema_total: int = 0
    failed_docs: int = 0
    latencies: list[int] = field(default_factory=list)
    field_hits: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    field_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    calibration: list[tuple[float, bool]] = field(default_factory=list)
    risk_tp: int = 0
    risk_fp: int = 0
    risk_fn: int = 0

    def metrics(self) -> dict[str, Any]:
        lat = sorted(self.latencies)
        p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else 0
        mean_s = (sum(lat) / len(lat) / 1000) if lat else 0
        accuracy = {f: round(self.field_hits[f] / n, 3) for f, n in self.field_total.items() if n}
        out: dict[str, Any] = {
            "schema_valid_rate": round(self.schema_ok / self.schema_total, 3)
            if self.schema_total
            else 0,
            "quarantine_rate": round(self.failed_docs / self.docs, 3) if self.docs else 0,
            "field_accuracy": accuracy,
            "mean_field_accuracy": round(statistics.mean(accuracy.values()), 3) if accuracy else 0,
            "latency_p50_ms": int(statistics.median(lat)) if lat else 0,
            "latency_p95_ms": int(p95),
            "docs_per_hour": round(3600 / mean_s, 1) if mean_s else None,
            "threshold_analysis": threshold_analysis(self.calibration),
        }
        if self.risk_tp + self.risk_fp + self.risk_fn:
            prec = self.risk_tp / max(1, self.risk_tp + self.risk_fp)
            rec = self.risk_tp / max(1, self.risk_tp + self.risk_fn)
            out["risk_precision"], out["risk_recall"] = round(prec, 3), round(rec, 3)
        return out


def threshold_analysis(points: list[tuple[float, bool]]) -> dict[str, dict[str, float]]:
    """For each threshold: share of fields auto-accepted and their accuracy (precision)."""
    out = {}
    for t in THRESHOLDS:
        accepted = [ok for conf, ok in points if conf >= t]
        out[str(t)] = {
            "auto_accept_rate": round(len(accepted) / len(points), 3) if points else 0.0,
            "auto_accept_precision": round(sum(accepted) / len(accepted), 3) if accepted else 0.0,
        }
    return out


def score_doc(acc: Accumulator, outcomes: list[Any], truth: dict[str, str]) -> None:
    acc.docs += 1
    acc.schema_total += len(outcomes)
    acc.schema_ok += sum(o.ok for o in outcomes)
    acc.failed_docs += any(not o.ok for o in outcomes)
    acc.latencies.append(sum(o.latency_ms for o in outcomes))
    by_schema = {o.schema_name: o for o in outcomes}
    fin = by_schema.get("FinancialHighlights")
    payload = fin.payload if fin and fin.ok and fin.payload else {}
    conf = fin.confidence if fin and fin.confidence else {}
    mult = _MULT.get(payload.get("units", "millions"), 1e6)
    for f in FIN_FIELDS:
        if f not in truth:
            continue
        raw = payload.get(f)
        pred = None if raw is None else float(raw) * mult
        ok = values_match(float(truth[f]), pred)
        acc.field_total[f] += 1
        acc.field_hits[f] += ok
        if f in conf:
            acc.calibration.append((float(conf[f]["score"]), ok))
    if "fiscal_year" in truth:
        acc.field_total["fiscal_year"] += 1
        acc.field_hits["fiscal_year"] += payload.get("fiscal_year") == int(
            float(truth["fiscal_year"])
        )
    if "risk_categories" in truth:
        risks = by_schema.get("RiskFactors")
        pred_cats = (
            {r["category"] for r in (risks.payload or {}).get("risks", [])}
            if risks and risks.ok
            else set()
        )
        true_cats = set(json.loads(truth["risk_categories"]))
        acc.risk_tp += len(pred_cats & true_cats)
        acc.risk_fp += len(pred_cats - true_cats)
        acc.risk_fn += len(true_cats - pred_cats)


def run_eval(
    models: list[str],
    prompt_versions: list[str] | None = None,
    limit: int | None = None,
    report_dir: Path = Path("docs/eval"),
) -> list[dict[str, Any]]:
    s = get_settings()
    gt = load_ground_truth(limit)
    results = []
    for model in models:
        for pv in prompt_versions or [s.prompt_version]:
            acc = Accumulator()
            tag = f"eval:{datetime.now(UTC):%Y%m%d%H%M}"
            error = None
            for accession, truth in gt.items():
                try:
                    outcomes = extract_filing(
                        accession,
                        model=model,
                        prompt_version=pv,
                        run_tag=tag,
                        create_reviews=False,
                    )
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    log.warning("eval.model_failed", model=model, error=error)
                    break
                score_doc(acc, outcomes, truth)
            metrics = acc.metrics() | {"error": error} if error else acc.metrics()
            with session_scope() as sess:
                run = EvalRun(model=model, prompt_version=pv, n_docs=acc.docs, metrics_json=metrics)
                sess.add(run)
            results.append(
                {"model": model, "prompt_version": pv, "n_docs": acc.docs, "metrics": metrics}
            )
            log.info("eval.done", model=model, prompt_version=pv, docs=acc.docs)
    write_report(results, report_dir, s.confidence_threshold)
    return results


def write_report(results: list[dict[str, Any]], report_dir: Path, threshold: float) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{datetime.now(UTC):%Y-%m-%d}.md"
    lines = [
        f"# Extraction eval - {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        "Ground truth: XBRL company facts (financial figures, 0.5% tolerance) + review corrections.",
        f"Configured confidence threshold: **{threshold}**.",
        "",
        "| model | prompt | docs | schema-valid | quarantine | revenue | net income | op. cash flow | fiscal year | p50 ms | p95 ms | docs/h |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        m = r["metrics"]
        fa = m.get("field_accuracy", {})
        lines.append(
            f"| {r['model']} | {r['prompt_version']} | {r['n_docs']} | {m.get('schema_valid_rate')} | "
            f"{m.get('quarantine_rate')} | {fa.get('revenue', '-')} | {fa.get('net_income', '-')} | "
            f"{fa.get('operating_cash_flow', '-')} | {fa.get('fiscal_year', '-')} | {m.get('latency_p50_ms')} | "
            f"{m.get('latency_p95_ms')} | {m.get('docs_per_hour')} |"
        )
    lines += ["", "## Confidence threshold analysis (financial fields)", ""]
    for r in results:
        lines += [
            f"**{r['model']} / {r['prompt_version']}**",
            "",
            "| threshold | auto-accept rate | precision of auto-accepted |",
            "|---|---|---|",
        ]
        for t, v in r["metrics"].get("threshold_analysis", {}).items():
            lines.append(f"| {t} | {v['auto_accept_rate']} | {v['auto_accept_precision']} |")
        if r["metrics"].get("error"):
            lines.append(f"\n> run aborted: {r['metrics']['error']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
