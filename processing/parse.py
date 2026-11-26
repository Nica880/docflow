"""Turn raw filing documents (HTML / iXBRL / PDF) into clean plain text."""

from __future__ import annotations

import io
import re
import unicodedata

from selectolax.lexbor import LexborHTMLParser as HTMLParser

_BLOCK_TAGS = r"p|div|br|tr|li|h[1-6]|table|section|article|ul|ol|hr|center|title"
_BLOCK_RE = re.compile(rf"<(/?(?:{_BLOCK_TAGS}))(?=[\s/>])", re.IGNORECASE)
_CELL_RE = re.compile(r"<(t[dh])(?=[\s/>])", re.IGNORECASE)
_SPACES = re.compile(r"[ \t\u00a0\u2009\u200b\u202f]+")
_BLANKS = re.compile(r"\n\s*\n\s*\n+")


class ParseError(ValueError):
    pass


def html_to_text(html: str | bytes) -> str:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    # Inline XBRL hides a big machine-readable header; it is not part of the document text.
    html = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", html)
    html = _BLOCK_RE.sub(lambda m: "\n<" + m.group(1), html)
    html = _CELL_RE.sub(lambda m: " \t<" + m.group(1), html)
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, head"):
        node.decompose()
    root = tree.body or tree.root
    if root is None:
        raise ParseError("empty HTML document")
    text = root.text(separator="", strip=False)
    return normalize_text(text)


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return normalize_text("\n".join(page.extract_text() or "" for page in reader.pages))


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = (
        text.replace("\r", "\n")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _BLANKS.sub("\n\n", text).strip()


def document_to_text(key: str, data: bytes) -> str:
    if key.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        text = pdf_to_text(data)
    else:
        text = html_to_text(data)
    if len(text) < 500:
        raise ParseError(f"document too short after parsing ({len(text)} chars)")
    return text
