"""Section chunks -> embeddings -> pgvector, and semantic search over them."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select

from core.config import get_settings
from core.db import session_scope
from core.logging import get_logger
from core.models import Company, Filing, Section, SectionChunk
from core.telemetry import pipeline_run
from processing.llm import get_embedder

log = get_logger(__name__)
EMBED_ITEMS = ("1", "1A", "1C", "7", "7A")


def chunk_text(text: str, size: int = 1500, overlap: int = 200) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            end = cut if cut > 0 else end
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def sections_to_embed(latest_only: bool) -> list[tuple[int, str, str]]:
    with session_scope() as s:
        q = (
            select(Section.id, Section.accession_no, Section.item, Filing.cik, Filing.filed_at)
            .join(Filing, Filing.accession_no == Section.accession_no)
            .where(Section.item.in_(EMBED_ITEMS), Filing.form_type != "INVOICE")
            .where(~select(SectionChunk.id).where(SectionChunk.section_id == Section.id).exists())
            .order_by(Filing.filed_at.desc())
        )
        rows = s.execute(q).all()
    if latest_only:
        latest: dict[int, str] = {}
        for _, acc, _, cik, _ in rows:
            latest.setdefault(cik, acc)
        rows = [r for r in rows if latest[r.cik] == r.accession_no]
    return [(r.id, r.accession_no, r.item) for r in rows]


def embed_sections(latest_only: bool | None = None, batch: int = 16) -> int:
    from processing.silver import load_section_text

    s = get_settings()
    embedder = get_embedder()
    todo = sections_to_embed(s.demo_embed_latest_only if latest_only is None else latest_only)
    total = 0
    with pipeline_run("embed_sections") as run:
        run.docs_in = len(todo)
        for section_id, acc, item in todo:
            text, _ = load_section_text(acc, item)
            chunks = chunk_text(text)[: s.embed_max_chunks_per_section]
            vectors: list[list[float]] = []
            for i in range(0, len(chunks), batch):
                vectors.extend(embedder.embed(chunks[i : i + batch]))
            with session_scope() as sess:
                sess.execute(delete(SectionChunk).where(SectionChunk.section_id == section_id))
                for idx, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True)):
                    sess.add(
                        SectionChunk(
                            section_id=section_id,
                            accession_no=acc,
                            item=item,
                            chunk_index=idx,
                            text=chunk,
                            embedding=vec,
                            model=embedder.model,
                        )
                    )
            total += len(chunks)
            run.docs_ok += 1
    log.info("embed.done", sections=len(todo), chunks=total)
    return total


@dataclass(frozen=True)
class SearchHit:
    accession_no: str
    item: str
    company: str | None
    ticker: str | None
    filed_at: str
    text: str
    score: float


def semantic_search(query: str, k: int = 5, ticker: str | None = None) -> list[SearchHit]:
    vec = get_embedder().embed([query])[0]
    distance = SectionChunk.embedding.cosine_distance(vec)
    with session_scope() as s:
        q = (
            select(SectionChunk, Company.name, Company.ticker, Filing.filed_at, distance.label("d"))
            .join(Filing, Filing.accession_no == SectionChunk.accession_no)
            .join(Company, Company.cik == Filing.cik)
            .order_by(distance)
            .limit(k)
        )
        if ticker:
            q = q.where(Company.ticker == ticker.upper())
        rows = s.execute(q).all()
        return [
            SearchHit(
                accession_no=chunk.accession_no,
                item=chunk.item,
                company=name,
                ticker=tick,
                filed_at=filed.isoformat(),
                text=chunk.text,
                score=round(1 - float(d), 4),
            )
            for chunk, name, tick, filed, d in rows
        ]
