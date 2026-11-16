import { writable, get } from 'svelte/store';
import type { Market, Meta, Resolved, Skill, Forecast } from './types';

export const markets = writable<Record<string, Market>>({});
export const order = writable<string[]>([]);
export const horizons = writable<string[]>([]);
export const resolved = writable<Resolved[]>([]);
export const skill = writable<Record<string, Record<string, Skill>>>({});
export const model = writable<{ version: string; trained_through?: string }>({ version: '—' });
export const status = writable<Record<string, any>>({});
export const conn = writable<'connecting' | 'live' | 'down'>('connecting');
export const serverTime = writable<number>(Date.now() / 1000);
export const selected = writable<string | null>(null);
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
  m.ribbon.push([f.ts, Object.fromEntries(Object.entries(f.h).map(([h, v]) => [h, v.p]))]);
  if (m.ribbon.length > 240) m.ribbon.shift();
}

function onMessage(msg: any) {
  lastMsg = Date.now();
  if (msg.ts) { offset = msg.ts - Date.now() / 1000; serverTime.set(msg.ts); }
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
        };
      }
      markets.set(out);
      order.set((msg.markets as Meta[]).map(m => m.sym));
      horizons.set(msg.horizons);
      skill.set(msg.model.skill || {});
      model.set({ version: msg.model.version, trained_through: msg.model.trained_through });
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
    case 'liq':
      markets.update(ms => {
        const m = ms[msg.sym];
        if (m) { m.liqs = [...m.liqs.slice(-19), { ts: msg.ts, side: msg.side, usd: msg.usd, price: msg.price }]; m.liqPulse = performance.now(); }
        return ms;
      });
      break;
  }
}

let ws: WebSocket | null = null;
let retry = 1000;
export function connect() {
  conn.set('connecting');
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { conn.set('live'); retry = 1000; };
  ws.onmessage = e => { try { onMessage(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  ws.onclose = e => {
    conn.set('down');
    if (e.code === 4401) { location.replace('/login'); return; }
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, 15000);
  };
  ws.onerror = () => ws?.close();
}
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
