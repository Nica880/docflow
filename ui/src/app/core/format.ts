export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  );
}

export function formatMetric(key: string, value: number): string {
  if (/rate|accuracy|precision|recall|f1/i.test(key) && value <= 1) {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (/_ms$/.test(key)) return `${Math.round(value)} ms`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export function errorMessage(err: unknown): string {
  if (!err) return 'Unknown error';
  if (typeof err === 'object') {
    const e = err as { status?: number; statusText?: string; message?: string; error?: unknown };
    const detail =
      typeof e.error === 'object' && e.error !== null && 'detail' in e.error
        ? JSON.stringify((e.error as { detail: unknown }).detail)
        : undefined;
    if (e.status !== undefined) {
      const text = e.statusText ? ` ${e.statusText}` : '';
      return `HTTP ${e.status}${text}${detail ? ` — ${detail}` : ''}`;
    }
    if (e.message) return e.message;
  }
  return String(err);
}

export const PALETTE = [
  '#4f7cff',
  '#22b07d',
  '#f5a524',
  '#e5484d',
  '#8e6cef',
  '#12a5c9',
  '#d66bb3',
  '#7c8a9e',
];
