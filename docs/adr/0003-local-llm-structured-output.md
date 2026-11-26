# ADR-0003: Local LLMs with schema-constrained output and a rules baseline

- Status: accepted

## Decision
- Ollama serves `qwen2.5:7b-instruct` (default) and `llama3.1:8b` (comparison). The Pydantic model's
  JSON Schema is passed as Ollama's `format`, so decoding is constrained to valid shapes.
- Output is validated with Pydantic; on failure the validation errors are sent back for up to two
  repair attempts, then the filing is quarantined (`quarantine.stage = extract:<schema>`).
- Long sections are compressed before prompting: keyword windows around financial-statement labels
  (Items 7/8) and first-sentence "headline" compression for risk factors (Item 1A).
- Prompts are versioned (`v1`, `v2`); every extraction stores model + prompt version.
- A deterministic regex/keyword extractor implements the same provider interface. It powers CI and
  the offline demo, and is reported as `rules-baseline` in every evaluation.

## Consequences
- No API keys, no cost, data never leaves the machine.
- 7–8B models are slower and weaker than hosted frontier models; the eval report quantifies the gap
  to the rules baseline and to XBRL ground truth instead of assuming quality.
