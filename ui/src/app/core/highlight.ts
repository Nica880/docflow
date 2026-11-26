import { Highlight } from './api.models';

export interface TextSegment {
  text: string;
  highlight: Highlight | null;
}

/**
 * Splits `text` into plain and highlighted segments. Highlights are clamped to the text
 * bounds, sorted by start offset, and overlapping ranges are dropped (first one wins).
 */
export function splitHighlights(text: string, highlights: readonly Highlight[]): TextSegment[] {
  const len = text.length;
  const valid = highlights
    .map((h) => ({ ...h, start: Math.max(0, h.start), end: Math.min(len, h.end) }))
    .filter((h) => h.end > h.start)
    .sort((a, b) => a.start - b.start || b.end - a.end);

  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const h of valid) {
    if (h.start < cursor) continue;
    if (h.start > cursor) segments.push({ text: text.slice(cursor, h.start), highlight: null });
    segments.push({ text: text.slice(h.start, h.end), highlight: h });
    cursor = h.end;
  }
  if (cursor < len) segments.push({ text: text.slice(cursor), highlight: null });
  return segments;
}
