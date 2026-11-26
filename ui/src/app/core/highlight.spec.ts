import { Highlight } from './api.models';
import { splitHighlights } from './highlight';

const hl = (start: number, end: number, field = 'f'): Highlight => ({
  field,
  value: 'v',
  snippet: '',
  start,
  end,
});

describe('splitHighlights', () => {
  it('returns the whole text as one plain segment when there are no highlights', () => {
    expect(splitHighlights('hello', [])).toEqual([{ text: 'hello', highlight: null }]);
  });

  it('splits around highlights in offset order regardless of input order', () => {
    const text = 'Revenue was $391B and net income $94B.';
    const a = hl(12, 17, 'revenue');
    const b = hl(33, 37, 'net_income');
    const segs = splitHighlights(text, [b, a]);
    expect(segs.map((s) => s.text)).toEqual([
      'Revenue was ',
      '$391B',
      ' and net income ',
      '$94B',
      '.',
    ]);
    expect(segs[1].highlight?.field).toBe('revenue');
    expect(segs[3].highlight?.field).toBe('net_income');
    expect(segs.map((s) => s.text).join('')).toBe(text);
  });

  it('drops overlapping and empty ranges and clamps out-of-bounds offsets', () => {
    const text = 'abcdefghij';
    const segs = splitHighlights(text, [hl(2, 6), hl(4, 8), hl(5, 5), hl(8, 99)]);
    expect(segs.map((s) => [s.text, !!s.highlight])).toEqual([
      ['ab', false],
      ['cdef', true],
      ['gh', false],
      ['ij', true],
    ]);
  });
});
