# ADR-0004: Field confidence and the human-review threshold

- Status: accepted

## Decision
Per-field confidence = `0.3 * model self-score + 0.4 * grounding + 0.3 * cross-checks`, where
- grounding = the quoted snippet appears verbatim in the source (partial credit if only its numbers
  or words do), halved if the value is not in its own snippet;
- cross-checks = domain rules (revenue > 0, |net income| and |cash flow| ≤ 2× revenue, fiscal year
  matches the period end, magnitude consistent with units; invoice line items sum to the subtotal,
  subtotal × VAT rate = VAT, subtotal + VAT = total).

Fields below `CONFIDENCE_THRESHOLD` (default **0.7**) become review tasks. Reviewer corrections are
applied in the gold marts and also stored as ground truth (`source = review`).

## Why 0.7
The eval report includes a threshold table (auto-accept rate vs. precision of auto-accepted fields
for 0.5–0.9). Self-scores alone are poorly calibrated in small models; grounding dominates, and 0.7
is the lowest threshold where an ungrounded value can never be auto-accepted
(max without grounding = 0.3 + 0.3 = 0.6). Re-evaluate with each new model/prompt version.
