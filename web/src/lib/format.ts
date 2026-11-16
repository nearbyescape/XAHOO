import type { Forecast } from './types';
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
/** Futures wording: probability of a higher close -> LONG / SHORT. */
export const side = (p: number) => (p >= 0.5 ? 'LONG' : 'SHORT');
/** How strong the lean is, in words: within 2 points of 50% = NEUTRAL, 2-5 points = SLIGHT, 5+ points = full. */
export const conviction = (p: number): 0 | 1 | 2 => { const d = Math.abs(p - 0.5); return d < 0.02 ? 0 : d < 0.05 ? 1 : 2; };
/** Direction shown: the server's steady label when present (it holds a side until the lean clearly fades), else
 *  the plain 2-point band. 1 UP, -1 DOWN, 0 NEUTRAL. */
export const dirOf = (p: number, lab?: number | null): -1 | 0 | 1 =>
  lab === 1 || lab === -1 || lab === 0 ? lab : conviction(p) === 0 ? 0 : p >= 0.5 ? 1 : -1;
/** Strength word for a shown side: SLIGHT under 55%, full from 55%. */
export const biasWord = (p: number, lab?: number | null) => {
  const d = dirOf(p, lab);
  return d === 0 ? 'NEUTRAL' : `${conviction(p) === 2 ? '' : 'SLIGHT '}${d > 0 ? 'LONG' : 'SHORT'}`;
};
/** The market's overall direction: the combined 5m–4h headline when the server sends one (coins); otherwise the
 *  longest shown timeframe (metals have no tested headline). null = no tested edge anywhere. */
export interface Overall { p: number; lab: number; tf: string; head: boolean; agree?: number; of?: number }
export function overall(f: Forecast | null | undefined): Overall | null {
  if (!f) return null;
  if (f.head) return { p: f.head.p, lab: f.head.lab, tf: 'overall', head: true, agree: f.head.agree, of: f.head.of };
  for (const h of ['4h', '1h', '15m', '5m']) {
    const x = f.h?.[h];
    if (x?.show) return { p: x.p, lab: dirOf(x.p, x.lab), tf: h, head: false };
  }
  return null;
}
export const biasShort = (p: number, lab?: number | null) => { const d = dirOf(p, lab); return d === 0 ? 'NEUTRAL' : d > 0 ? 'LONG' : 'SHORT'; };
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
