export const HORIZON_MIN: Record<string, number> = { '1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440 };
export function px(v: number | null | undefined, digits: number): string {
  if (v == null || !isFinite(v)) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export function pct(v: number | null | undefined, d = 2): string {
  if (v == null || !isFinite(v)) return '—';
  return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d) + '%';
}
export function usd(v: number): string {
  const a = Math.abs(v);
  const s = a >= 1e9 ? (a / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0);
  return (v < 0 ? '−' : '+') + '$' + s;
}
/** Probability → colour. 50% is a cool neutral; the colour saturates by about 57% / 43%, the range the
 *  calibrated probabilities actually span. */
export const FULL = 0.07;
const UP = [46, 230, 168], DOWN = [255, 92, 138], NEUTRAL = [139, 149, 178];
export const lean = (p: number) => Math.max(-1, Math.min(1, (p - 0.5) / FULL));
export function probColor(p: number, alpha = 1): string {
  const d = lean(p), s = Math.abs(d), t = d >= 0 ? UP : DOWN, k = 0.18 + 0.82 * s;
  const c = NEUTRAL.map((n, i) => Math.round(n + (t[i] - n) * k));
  return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${alpha})`;
}
export function probBg(p: number, max = 0.2): string {
  const d = lean(p), t = d >= 0 ? UP : DOWN;
  return `rgba(${t[0]}, ${t[1]}, ${t[2]}, ${(0.015 + max * Math.abs(d)).toFixed(3)})`;
}
export const probText = (p: number, d = 0) => `${p >= 0.5 ? '▲' : '▼'} ${((p >= 0.5 ? p : 1 - p) * 100).toFixed(d)}%`;
export function clock(ts: number, tz = 'UTC'): string {
  return new Date(ts * 1000).toLocaleTimeString('en-GB', { timeZone: tz, hour12: false });
}
export function ago(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}
/** Badge colours per market (plain palette, no logos). */
export const BADGE: Record<string, [string, string]> = {
  BTCUSDT: ['#ffb547', '#ff7a45'], ETHUSDT: ['#8b7cff', '#5e7bff'], SOLUSDT: ['#9b6bff', '#2ee6c8'],
  XRPUSDT: ['#8fa3c8', '#5c6f99'], BNBUSDT: ['#f6c453', '#e0a43a'], DOGEUSDT: ['#e8c27a', '#c99a4b'],
  ADAUSDT: ['#4e8cff', '#2f5fd6'], LINKUSDT: ['#4c7dff', '#38c6f4'], XAUUSDT: ['#ffd76a', '#d9a521'], XAGUSDT: ['#e3e8f2', '#9aa6bd'],
};
