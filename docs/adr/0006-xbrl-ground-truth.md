# ADR-0006: XBRL company facts as ground truth for financial figures

- Status: accepted

## Context
Hand-labelling financial figures for hundreds of filings is slow and error-prone.

## Decision
Use the SEC's XBRL `companyfacts` API — numbers filed by the companies themselves — as ground truth
for revenue, net income and operating cash flow: the annual (350–380 day) 10-K fact whose accession
number and period end match the filing. Reviewer corrections override XBRL; optional hand labels
(`source = hand`, e.g. risk categories) override both. Match = within 0.5% after unit scaling.

## Consequences
Ground truth scales to every ingested filing for free. Caveats: banks report revenue under
different concepts (`RevenuesNetOfInterestExpense`), some figures live in exhibits rather than the
10-K body (e.g. JPMorgan), and XBRL tags can differ from the headline line the model reads — these
show up as mismatches and are worth inspecting in the review queue.
