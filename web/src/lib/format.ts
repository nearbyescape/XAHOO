export const HORIZON_MIN: Record<string, number> = { '1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440 };

export function px(v: number | null | undefined, digits: number): string {
  if (v == null || !isFinite(v)) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export function pct(v: number | null | undefined, d = 2): string {
  if (v == null || !isFinite(v)) return '—';
  return (v > 0 ? '+' : '') + v.toFixed(d) + '%';
}
export function usd(v: number): string {
  const a = Math.abs(v);
  const s = a >= 1e9 ? (a / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0);
  return (v < 0 ? '−' : '') + '$' + s;
}
/** Probability → colour. 50% is neutral grey; the colour saturates by about 57% / 43%, the range the
 *  calibrated probabilities actually span. */
export const FULL = 0.07;
export function probColor(p: number, alpha = 1): string {
  const d = Math.max(-1, Math.min(1, (p - 0.5) / FULL));
  const s = Math.abs(d);
  const [r, g, b] = d >= 0 ? [43, 209, 126] : [255, 91, 110];
  const mix = (c: number, n: number) => Math.round(n + (c - n) * (0.25 + 0.75 * s));
  return `rgba(${mix(r, 120)}, ${mix(g, 132)}, ${mix(b, 148)}, ${alpha})`;
}
export function probBg(p: number): string {
  const d = Math.max(-1, Math.min(1, (p - 0.5) / FULL));
  const [r, g, b] = d >= 0 ? [43, 209, 126] : [255, 91, 110];
  return `rgba(${r}, ${g}, ${b}, ${(0.02 + 0.26 * Math.abs(d)).toFixed(3)})`;
}
export function clock(ts: number, tz = 'UTC'): string {
  return new Date(ts * 1000).toLocaleTimeString('en-GB', { timeZone: tz, hour12: false });
}
export function ago(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}
