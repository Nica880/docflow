"""Split 10-K plain text into its standard Items (1, 1A, 1C, 7, 7A, 8, ...).

Every 10-K repeats the item headings in its table of contents, and some reference items inline
("see Item 7"). For each item we therefore keep the heading occurrence that opens the *longest*
section (up to the next heading), which is the body rather than the ToC entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ITEMS: dict[str, str] = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}

# Items kept in silver (the ones downstream consumers use).
KEEP = ("1", "1A", "1C", "7", "7A", "8")

SCHEMA_VERSION = "1"

_HEADING = re.compile(
    r"^[ \t]*(?:PART\s+[IV]+[\s.,:-]*)?ITEM[ \t\u00a0]*(\d{1,2}[A-C]?)[ \t]*[.:\-\u2013\u2014]?",
    re.IGNORECASE | re.MULTILINE,
)
MIN_SECTION_CHARS = 200


@dataclass(frozen=True)
class SectionText:
    item: str
    title: str
    text: str

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.text) // 4)


def find_headings(text: str) -> list[tuple[int, str]]:
    """Heading positions; repeated consecutive headings of one item (page running headers such
    as "PART I / Item 1A" on every page) collapse into the first occurrence."""
    out: list[tuple[int, str]] = []
    for m in _HEADING.finditer(text):
        item = m.group(1).upper()
        if item in ITEMS and not (out and out[-1][1] == item):
            out.append((m.start(), item))
    return out


def split_items(text: str, keep: tuple[str, ...] | None = KEEP) -> list[SectionText]:
    headings = find_headings(text)
    if not headings:
        return []
    best: dict[str, tuple[int, int]] = {}
    for idx, (pos, item) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(text)
        length = end - pos
        if item not in best or length > best[item][1] - best[item][0]:
            best[item] = (pos, end)
    sections: list[SectionText] = []
    for item, (start, end) in sorted(best.items(), key=lambda kv: kv[1][0]):
        if keep is not None and item not in keep:
            continue
        body = text[start:end].strip()
        if len(body) < MIN_SECTION_CHARS:
            continue
        sections.append(SectionText(item=item, title=ITEMS[item], text=body))
    return sections
