import { writable, get } from 'svelte/store';
import type { Market, Meta, Resolved, Skill, Forecast, Big, Alert } from './types';

export const markets = writable<Record<string, Market>>({});
export const order = writable<string[]>([]);
export const horizons = writable<string[]>([]);
export const resolved = writable<Resolved[]>([]);
export const skill = writable<Record<string, Record<string, Skill>>>({});
export const model = writable<{ version: string; trained_through?: string }>({ version: '—' });
export const status = writable<Record<string, any>>({});
export const conn = writable<'connecting' | 'live' | 'polling' | 'down'>('connecting');
export const connError = writable<string>('');
export const serverTime = writable<number>(Date.now() / 1000);
export const selected = writable<string | null>(null);
export const levelsInfo = writable<any>(null);
export const focus = writable<string>('BTCUSDT');
export const fh = writable<string>('1h');            // horizon the focus panel explains
export const bigUsd = writable<Record<string, number>>({});
export const alertSpec = writable<{ z_min: number; avg_p: number; skill?: Record<string, any> } | null>(null);
/** Insert or update alerts for a market (by id), oldest first, keeping the last 3 days. */
export function mergeAlerts(sym: string, list: Alert[]) {
  markets.update(ms => {
    const m = ms[sym];
    if (!m) return ms;
    const by = new Map(m.alerts.map(a => [a.id, a]));
    for (const a of list) by.set(a.id, { ...by.get(a.id), ...a, end: a.end ?? a.t0 + 3600 });
    const cut = now() - 3 * 86400;
    m.alerts = [...by.values()].filter(a => a.t0 >= cut).sort((x, y) => x.t0 - y.t0);
    return ms;
  });
}
export const tally = writable<{ hit: number; n: number }>({ hit: 0, n: 0 });   // forecasts resolved since this page opened

let offset = 0;            // server clock − local clock (replay mode runs on a simulated clock)
let lastMsg = 0;
export const now = () => Date.now() / 1000 + offset;

function applyForecast(m: Market, f: Forecast | null) {
  if (!f || !f.h) return;
  const prev = m.forecast;
  const t = performance.now();
  for (const h of Object.keys(f.h)) {
    const before = prev?.h?.[h]?.p;
    const big = h === '1m' || h === '5m' ? 0.045 : 0.03;      // short horizons move more: flash only on larger jumps
    if (before != null && f.h[h].show && Math.abs(f.h[h].p - before) >= big) m.changed[h] = t;
  }
  m.forecast = f;
  if (f.ref) { m.spark.push(f.ref); if (m.spark.length > 180) m.spark.shift(); }
  m.ribbon.push([f.ts, Object.fromEntries(Object.entries(f.h).map(([h, v]) => [h, v.p]))]);
  if (m.ribbon.length > 240) m.ribbon.shift();
}

function onMessage(msg: any) {
  lastMsg = Date.now();
  // only the server-clock messages set the clock: big trades and liquidations carry their own time in milliseconds
  if (msg.ts && (msg.type === 'snapshot' || msg.type === 'tick' || msg.type === 'forecast') && msg.ts < 1e11) {
    offset = msg.ts - Date.now() / 1000; serverTime.set(msg.ts);
  }
  switch (msg.type) {
    case 'snapshot': {
      const out: Record<string, Market> = {};
      for (const meta of msg.markets as Meta[]) {
        const s = msg.m[meta.sym] || {};
        out[meta.sym] = {
          ...meta, price: s.price ?? null, mark: s.mark ?? null, dayAgo: s.day_ago ?? null,
          forecast: s.forecast && s.forecast.h ? s.forecast : null, ribbon: s.ribbon || [], spark: s.spark || [],
          b5: 0, s5: 0, b60: 0, s60: 0, funding: s.funding ?? null, oiChg1h: s.oi_chg_1h ?? null, lsRatio: s.ls_ratio ?? null,
          liqs: s.liqs || [], age: null, changed: {}, liqPulse: 0,
          nextFunding: null,
          big: s.big || [], big15: s.big15 || [0, 0], book: s.book && s.book.mid ? s.book : null, bigPulse: 0,
          alerts: (s.alerts || []).map((a: Alert) => ({ ...a, end: a.t0 + 3600 })),
        };
      }
      markets.set(out);
      order.set((msg.markets as Meta[]).map(m => m.sym));
      horizons.set(msg.horizons);
      skill.set(msg.model.skill || {});
      levelsInfo.set(msg.model.levels || null);
      bigUsd.set(msg.big_usd || {});
      model.set({ version: msg.model.version, trained_through: msg.model.trained_through });
      alertSpec.set(msg.model.alerts || null);
      status.set(msg.status || {});
      resolved.set((msg.resolved || []).slice().reverse());
      break;
    }
    case 'tick':
      markets.update(ms => {
        for (const [sym, t] of Object.entries(msg.m as Record<string, any>)) {
          const m = ms[sym];
          if (!m) continue;
          if (t.price != null) m.price = t.price;
          if (t.mark != null) m.mark = t.mark;
          m.b5 = t.b5; m.s5 = t.s5; m.b60 = t.b60; m.s60 = t.s60; m.age = t.age;
          if (t.funding != null) m.funding = t.funding;
          if (t.big15) m.big15 = t.big15;
          if (t.next_funding) m.nextFunding = t.next_funding;
        }
        return ms;
      });
      break;
    case 'forecast':
      markets.update(ms => {
        for (const [sym, f] of Object.entries(msg.markets as Record<string, Forecast>)) if (ms[sym]) applyForecast(ms[sym], f);
        return ms;
      });
      break;
    case 'resolved': {
      const items = msg.items as Resolved[];
      resolved.update(r => [...items.slice().reverse(), ...r].slice(0, 120));
      tally.update(t => ({ n: t.n + items.length, hit: t.hit + items.filter(i => (i.p > 0.5) === (i.outcome === 1)).length }));
      break;
    }
    case 'alert':
      mergeAlerts(msg.alert.sym, [msg.alert as Alert]);
      break;
    case 'big':
      markets.update(ms => {
        const m = ms[msg.sym];
        if (m) { m.big = [...m.big.slice(-59), { ts: msg.ts, side: msg.side, usd: msg.usd, price: msg.price, sim: msg.sim } as Big]; m.bigPulse = performance.now(); }
        return ms;
      });
      break;
    case 'book':
      markets.update(ms => { const m = ms[msg.sym]; if (m) m.book = msg.book; return ms; });
      break;
    case 'liq':
      markets.update(ms => {
        const m = ms[msg.sym];
        if (m) { m.liqs = [...m.liqs.slice(-19), { ts: msg.ts, side: msg.side, usd: msg.usd, price: msg.price }]; m.liqPulse = performance.now(); }
        return ms;
      });
      break;
  }
}

// Live updates come over a WebSocket. If it cannot connect (for example a proxy that does not pass WebSocket
// upgrades), the page falls back to fetching the same updates over HTTPS every 1.5 s, and keeps retrying the
// WebSocket in the background; it switches back as soon as the socket opens.
let ws: WebSocket | null = null;
let retry = 1000;
let fails = 0;
let poll: ReturnType<typeof setInterval> | null = null;
let lastForecast = 0;
export function connect() {
  if (get(conn) !== 'polling') conn.set('connecting');
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { stopPolling(); conn.set('live'); connError.set(''); retry = 1000; fails = 0; };
  ws.onmessage = e => { try { onMessage(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  ws.onclose = e => {
    if (e.code === 4401) { location.replace('/login'); return; }
    fails += 1;
    if (fails >= 2) startPolling(); else if (get(conn) !== 'polling') conn.set('down');
    setTimeout(connect, fails >= 2 ? 30000 : retry);
    retry = Math.min(retry * 2, 15000);
  };
  ws.onerror = () => ws?.close();
}
async function pollOnce(full: boolean) {
  try {
    if (full) { onMessage(await api<any>('/api/snapshot')); lastForecast = 0; }
    const t = await api<any>('/api/tick');
    onMessage(t);
    if (t.forecast_ts && t.forecast_ts !== lastForecast) {
      const f = await api<any>(`/api/forecasts`);
      if (lastForecast) onMessage(f);          // the snapshot already carried the current forecast
      lastForecast = t.forecast_ts;
    }
    if (get(conn) !== 'live') conn.set('polling');
    connError.set('');
  } catch (err) {
    if (get(conn) !== 'live') conn.set('down');
    connError.set(String((err as Error).message || err));
  }
}
function startPolling() {
  if (poll) return;
  pollOnce(true);
  let n = 0;
  poll = setInterval(() => { n += 1; pollOnce(n % 200 === 0); }, 1500);      // full refresh every 5 minutes
}
function stopPolling() { if (poll) { clearInterval(poll); poll = null; } }
// if the socket goes quiet (laptop sleep, network change) reconnect
setInterval(() => { if (get(conn) === 'live' && lastMsg && Date.now() - lastMsg > 15000) ws?.close(); }, 5000);
// a 401 on the socket handshake shows up as a plain close: check the session over HTTP
export async function checkAuth() {
  try { const r = await fetch('/api/health'); if (r.status === 401) location.replace('/login'); } catch { /* offline */ }
}

export async function api<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin' });
  if (r.status === 401) { location.replace('/login'); throw new Error('login required'); }
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
