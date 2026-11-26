"""LLM extraction: context -> schema-constrained JSON -> validation/repair -> confidence -> review.

Rules (docs/PLAN.md §5): JSON-schema constrained output, Pydantic validation, up to 2 repair
retries, then quarantine. Field confidence = model self-score blended with validation signals
(grounding of the quoted snippet in the source text + domain cross-checks).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.metrics import EXTRACTION_LATENCY, EXTRACTIONS
from core.models import Company, Extraction, Filing, ReviewTask, Section
from core.telemetry import tracer
from processing import context as ctx
from processing.llm import LLMProvider, get_provider
from processing.prompts import get_prompt
from processing.schemas import (
    SCHEMA_VERSION,
    SCHEMAS,
    FinancialHighlights,
    Invoice,
    Leadership,
    RiskFactors,
    json_schema,
)

log = get_logger(__name__)
MAX_REPAIRS = 2


class ExtractionFailed(RuntimeError):
    def __init__(self, message: str, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


@dataclass
class RawExtraction:
    obj: BaseModel
    attempts: int
    latency_ms: int
    model: str


@dataclass
class FieldScore:
    score: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"score": round(self.score, 3), "reasons": self.reasons}


def run_llm(
    provider: LLMProvider, schema_name: str, context_text: str, prompt_version: str
) -> RawExtraction:
    model_cls = SCHEMAS[schema_name]
    prompt = get_prompt(prompt_version, schema_name)
    messages = [{"role": "user", "content": prompt.user.format(context=context_text)}]
    latency = 0
    last_error = ""
    for attempt in range(1, MAX_REPAIRS + 2):
        result = provider.complete_json(prompt.system, messages, json_schema(schema_name))
        latency += result.latency_ms
        try:
            obj = model_cls.model_validate_json(result.content)
            return RawExtraction(obj, attempt, latency, result.model)
        except ValidationError as exc:
            last_error = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:10]
            )
            messages += [
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": f"That JSON is invalid: {last_error}. Return only corrected JSON.",
                },
            ]
    raise ExtractionFailed(f"schema validation failed after repairs: {last_error}", MAX_REPAIRS + 1)


# --- confidence -----------------------------------------------------------------------------------

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s.lower()).strip()


def grounded(snippet: str | None, source: str) -> float:
    """1.0 if the snippet is quoted verbatim, partial credit if its numbers/words appear."""
    if not snippet:
        return 0.0
    s, src = _norm(snippet), _norm(source)
    if s and s in src:
        return 1.0
    nums = re.findall(r"\d[\d,]*\.?\d*", s)
    if nums:
        return sum(n in src for n in nums) / len(nums) * 0.8
    words = [w for w in re.findall(r"[a-z]{4,}", s)][:20]
    return (sum(w in src for w in words) / len(words) * 0.6) if words else 0.0


def value_in_snippet(value: float | None, snippet: str | None) -> bool:
    if value is None or not snippet:
        return False
    digits = re.sub(r"[^\d]", "", snippet)
    v = abs(value)
    candidates = {f"{v:.0f}", f"{v:.1f}".replace(".", ""), f"{v:.2f}".replace(".", "")}
    return any(c and c in digits for c in candidates)


def blend(self_conf: float, ground: float, checks: float) -> float:
    return max(0.0, min(1.0, 0.3 * self_conf + 0.4 * ground + 0.3 * checks))


def score_financials(
    obj: FinancialHighlights, source: str, period_end: date | None
) -> dict[str, FieldScore]:
    scores: dict[str, FieldScore] = {}
    rev = obj.normalized("revenue")
    year_ok = period_end is None or obj.fiscal_year in (period_end.year, period_end.year - 1)
    scores["fiscal_year"] = FieldScore(
        blend(obj.self_confidence, 1.0 if year_ok else 0.0, 1.0 if year_ok else 0.0),
        [] if year_ok else ["fiscal year does not match the period end date"],
    )
    for name in FinancialHighlights.FIELDS:
        value = getattr(obj, name)
        snippet = getattr(obj, f"{name}_snippet")
        reasons: list[str] = []
        if value is None:
            scores[name] = FieldScore(0.0, ["value not found"])
            continue
        g = grounded(snippet, source)
        if g < 1.0:
            reasons.append("snippet not quoted verbatim" if g > 0 else "snippet not in source")
        if not value_in_snippet(value, snippet):
            g *= 0.5
            reasons.append("value not present in snippet")
        checks = [year_ok]
        norm = obj.normalized(name) or 0.0
        if name == "revenue":
            checks.append(norm > 0)
            if norm <= 0:
                reasons.append("revenue must be positive")
        elif rev:
            plausible = abs(norm) <= 2 * rev
            checks.append(plausible)
            if not plausible:
                reasons.append(f"{name} implausibly large vs revenue")
        if norm and abs(norm) < 1e5:
            checks.append(False)
            reasons.append("magnitude too small - check units")
        scores[name] = FieldScore(blend(obj.self_confidence, g, sum(checks) / len(checks)), reasons)
    return scores


def score_risks(obj: RiskFactors, source: str) -> dict[str, FieldScore]:
    scores: dict[str, FieldScore] = {}
    for i, risk in enumerate(obj.risks):
        g = grounded(risk.snippet, source)
        reasons = [] if g >= 1.0 else ["snippet not quoted verbatim"]
        checks = 1.0 if risk.category != "other" else 0.5
        if risk.category == "other":
            reasons.append("uncategorised risk")
        scores[f"risks[{i}].category"] = FieldScore(blend(obj.self_confidence, g, checks), reasons)
    if not obj.risks:
        scores["risks"] = FieldScore(0.0, ["no risks extracted"])
    return scores


def score_leadership(obj: Leadership, source: str) -> dict[str, FieldScore]:
    out: dict[str, FieldScore] = {}
    for name in ("ceo", "cfo"):
        value = getattr(obj, name)
        if value is None:
            out[name] = FieldScore(0.0, ["value not found"])
            continue
        g = grounded(getattr(obj, f"{name}_snippet"), source)
        in_snip = value.lower() in (getattr(obj, f"{name}_snippet") or "").lower()
        out[name] = FieldScore(blend(obj.self_confidence, g, 1.0 if in_snip else 0.0))
    return out


def score_invoice(obj: Invoice, source: str) -> dict[str, FieldScore]:
    line_sum = round(sum(li.amount for li in obj.line_items), 2)
    sub_ok = abs(line_sum - obj.subtotal) <= 0.01
    vat_ok = abs(obj.subtotal * obj.vat_rate - obj.vat_amount) <= 0.05
    total_ok = abs(obj.subtotal + obj.vat_amount - obj.total) <= 0.01
    src = _norm(source)

    def present(v: object) -> float:
        return 1.0 if _norm(str(v)) in src else 0.0

    def fmt(v: float) -> str:
        return f"{v:,.2f}"

    out = {
        "vendor": FieldScore(blend(obj.self_confidence, present(obj.vendor), 1.0)),
        "invoice_number": FieldScore(blend(obj.self_confidence, present(obj.invoice_number), 1.0)),
        "invoice_date": FieldScore(blend(obj.self_confidence, present(obj.invoice_date), 1.0)),
        "subtotal": FieldScore(
            blend(obj.self_confidence, present(fmt(obj.subtotal)), float(sub_ok)),
            [] if sub_ok else [f"line items sum to {line_sum}, not {obj.subtotal}"],
        ),
        "vat_amount": FieldScore(
            blend(obj.self_confidence, present(fmt(obj.vat_amount)), float(vat_ok)),
            [] if vat_ok else ["VAT amount != subtotal x VAT rate"],
        ),
        "total": FieldScore(
            blend(obj.self_confidence, present(fmt(obj.total)), float(total_ok)),
            [] if total_ok else ["subtotal + VAT != total"],
        ),
    }
    return out


def field_value(obj: BaseModel, name: str) -> str | None:
    m = re.fullmatch(r"risks\[(\d+)\]\.category", name)
    if m and isinstance(obj, RiskFactors):
        risk = obj.risks[int(m.group(1))]
        return f"{risk.category}: {risk.summary}"
    value = getattr(obj, name, None)
    return None if value is None else str(value)


# --- orchestration ------------------------------------------------------------------------------


@dataclass
class FilingContext:
    accession_no: str
    company: str | None
    form_type: str
    period_end: date | None
    sections: dict[str, str]


def load_filing_context(accession_no: str) -> FilingContext:
    from processing.silver import load_section_text

    with session_scope() as s:
        filing = s.get(Filing, accession_no)
        if filing is None:
            raise KeyError(accession_no)
        company = s.get(Company, filing.cik)
        items = list(s.scalars(select(Section.item).where(Section.accession_no == accession_no)))
        info = (company.name if company else None, filing.form_type, filing.period_end)
    sections = {item: load_section_text(accession_no, item)[0] for item in items}
    return FilingContext(accession_no, info[0], info[1], info[2], sections)


def build_context(schema_name: str, fc: FilingContext) -> str:
    items = ctx.SOURCE_ITEMS[schema_name]
    body = ctx.BUILDERS[schema_name](fc.sections)
    return ctx.header(fc.company, fc.form_type, fc.period_end, "/".join(items)) + body


def score(
    schema_name: str, obj: BaseModel, source: str, period_end: date | None
) -> dict[str, FieldScore]:
    if isinstance(obj, FinancialHighlights):
        return score_financials(obj, source, period_end)
    if isinstance(obj, RiskFactors):
        return score_risks(obj, source)
    if isinstance(obj, Leadership):
        return score_leadership(obj, source)
    if isinstance(obj, Invoice):
        return score_invoice(obj, source)
    raise ValueError(schema_name)


@dataclass
class Outcome:
    schema_name: str
    ok: bool
    extraction_id: int | None = None
    review_tasks: int = 0
    latency_ms: int = 0
    attempts: int = 0
    error: str | None = None
    payload: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None


def extract_and_store(
    accession_no: str,
    schema_name: str,
    source_text: str,
    period_end: date | None,
    provider: LLMProvider,
    prompt_version: str,
    run_tag: str = "pipeline",
    create_reviews: bool = True,
) -> Outcome:
    threshold = get_settings().confidence_threshold
    with tracer(__name__).start_as_current_span("extract") as span:
        span.set_attribute("docflow.accession_no", accession_no)
        span.set_attribute("docflow.schema", schema_name)
        try:
            raw = run_llm(provider, schema_name, source_text, prompt_version)
        except Exception as exc:
            EXTRACTIONS.labels(schema=schema_name, outcome="failed").inc()
            attempts = exc.attempts if isinstance(exc, ExtractionFailed) else 1
            return Outcome(
                schema_name, ok=False, attempts=attempts, error=f"{type(exc).__name__}: {exc}"
            )
        scores = score(schema_name, raw.obj, source_text, period_end)
        overall = sum(f.score for f in scores.values()) / max(1, len(scores))
        confidence = {k: v.as_dict() for k, v in scores.items()} | {"overall": round(overall, 3)}
        payload = raw.obj.model_dump(mode="json")
        EXTRACTIONS.labels(schema=schema_name, outcome="ok").inc()
        EXTRACTION_LATENCY.labels(model=raw.model).observe(raw.latency_ms / 1000)
        with session_scope() as s:
            ext = Extraction(
                accession_no=accession_no,
                schema_name=schema_name,
                schema_version=SCHEMA_VERSION,
                model=raw.model,
                prompt_version=prompt_version,
                payload_json=payload,
                confidence_json=confidence,
                attempts=raw.attempts,
                latency_ms=raw.latency_ms,
                run_tag=run_tag,
            )
            s.add(ext)
            s.flush()
            n_reviews = 0
            if create_reviews:
                for name, fs in scores.items():
                    if fs.score < threshold:
                        s.add(
                            ReviewTask(
                                extraction_id=ext.id,
                                field=name,
                                value=field_value(raw.obj, name),
                                confidence=round(fs.score, 3),
                                reason="; ".join(fs.reasons) or "below confidence threshold",
                            )
                        )
                        n_reviews += 1
            ext_id = ext.id
        return Outcome(
            schema_name,
            ok=True,
            extraction_id=ext_id,
            review_tasks=n_reviews,
            latency_ms=raw.latency_ms,
            attempts=raw.attempts,
            payload=payload,
            confidence=confidence,
        )


def extract_filing(
    accession_no: str,
    schemas: tuple[str, ...] | list[str] = ("FinancialHighlights", "RiskFactors"),
    model: str | None = None,
    prompt_version: str | None = None,
    run_tag: str = "pipeline",
    create_reviews: bool = True,
) -> list[Outcome]:
    from processing.silver import quarantine

    s = get_settings()
    provider = get_provider(model)
    pv = prompt_version or s.prompt_version
    fc = load_filing_context(accession_no)
    outcomes = []
    for schema_name in schemas:
        source = build_context(schema_name, fc)
        outcome = extract_and_store(
            accession_no, schema_name, source, fc.period_end, provider, pv, run_tag, create_reviews
        )
        outcomes.append(outcome)
        if not outcome.ok and run_tag == "pipeline":
            quarantine(accession_no, f"extract:{schema_name}", outcome.error or "unknown")
    if run_tag == "pipeline" and all(o.ok for o in outcomes):
        with session_scope() as sess:
            filing = sess.get(Filing, accession_no)
            if filing is not None:
                filing.status = "extracted"
    log.info(
        "extract.filing",
        accession=accession_no,
        model=provider.model,
        ok=sum(o.ok for o in outcomes),
        reviews=sum(o.review_tasks for o in outcomes),
    )
    return outcomes
