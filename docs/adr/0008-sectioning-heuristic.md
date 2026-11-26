# ADR-0008: Sectioning 10-K filings without an ML model

- Status: accepted

## Decision
Convert HTML/iXBRL to text while preserving block boundaries (inline XBRL header dropped), find
`Item N[A-C]` headings at line starts, collapse consecutive repeats of the same item (page running
headers) and, for each item, keep the occurrence that opens the longest span — the body rather than
the table-of-contents entry. Items 1, 1A, 1C, 7, 7A and 8 are kept.

## Consequences
Deterministic, fast and testable on real filings (fixtures for Apple, Microsoft, NVIDIA, JPMorgan,
Goldman Sachs). Filings that incorporate items by reference (e.g. MD&A in an exhibit) yield short
sections; extraction then reports missing values that land in the review queue.
