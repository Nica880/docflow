from __future__ import annotations

from processing.context import headline_compress, keyword_windows
from processing.parse import html_to_text
from processing.sectioning import split_items


def test_html_to_text_keeps_block_boundaries_and_drops_ixbrl_header() -> None:
    html = (
        "<html><body><ix:header><ix:hidden>HIDDEN-XBRL</ix:hidden></ix:header>"
        "<div><span>Item</span><span> 1A.</span> Risk Factors</div><p>First&nbsp;para.</p>"
        "<table><tr><td>Total net sales</td><td>$ 416,161</td></tr></table>"
        + "<p>filler text</p>" * 60
        + "</body></html>"
    )
    text = html_to_text(html)
    assert "HIDDEN-XBRL" not in text
    assert "Item 1A. Risk Factors" in text
    assert "First para." in text
    assert "Total net sales" in text and "416,161" in text


def test_sectioning_skips_table_of_contents() -> None:
    body = "x " * 300
    text = (
        "Item 1. Business 3\nItem 1A. Risk Factors 10\nItem 7. MD&A 30\n"
        f"Item 1. Business\n{body}\nItem 1A. Risk Factors\n{body * 2}\n"
        f"Item 7. Management's Discussion\n{body}\nItem 8. Financial Statements\n{body}"
    )
    sections = {s.item: s for s in split_items(text)}
    assert set(sections) == {"1", "1A", "7", "8"}
    assert sections["1A"].text.startswith("Item 1A. Risk Factors\n")
    assert len(sections["1A"].text) > 1000


def test_sectioning_real_apple_10k(aapl_text: str) -> None:
    sections = {s.item: s for s in split_items(aapl_text)}
    assert {"1", "1A", "1C", "7", "7A", "8"} <= set(sections)
    assert "Risk Factors" in sections["1A"].text[:100]
    assert len(sections["8"].text) > 30_000


def test_sectioning_collapses_running_page_headers(msft_text: str) -> None:
    # Microsoft repeats "PART I / Item 1A" at the top of every page of its risk factors.
    sections = {s.item: s for s in split_items(msft_text)}
    assert len(sections["1A"].text) > 50_000


def test_keyword_windows_merge_overlaps() -> None:
    import re

    text = "a\n" * 50 + "net income 1\nnet income 2\n" + "b\n" * 50
    out = keyword_windows(text, re.compile(r"net income"), 5, 5, 1000)
    assert out.count("...") == 0 and "net income 1" in out and "net income 2" in out


def test_headline_compress_keeps_first_sentences() -> None:
    text = (
        "Our business depends on suppliers. Long explanation that should go away.\n\n"
        "Cyber attacks could harm us. More detail."
    )
    assert (
        headline_compress(text)
        == "Our business depends on suppliers.\nCyber attacks could harm us."
    )
