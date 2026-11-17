<script lang="ts">
  // Focus chart. Layout, so nothing sits on top of the candles:
  //   candle area   candles, support / resistance lines, direction line, expected range (optional)
  //   strips below  big trades per candle (net) and volume per candle (buyers up, sellers down)
  //   flow column   right of the price axis, on the same price scale: 24h volume by price (sellers left,
  //                 buyers right) with buyer / seller zones, order-book walls, and live buy / sell totals
  import Arrow from './Arrow.svelte';
  import { onMount, onDestroy } from 'svelte';
  import { tweened } from 'svelte/motion';
  import { fly, scale } from 'svelte/transition';
  import CoinLogo from './CoinLogo.svelte';
  import { cubicOut, backOut } from 'svelte/easing';
  import { createChart, type IChartApi, type ISeriesApi, type IPriceLine, LineStyle } from 'lightweight-charts';
  import { api, markets, fh, bigUsd, serverTime } from '../lib/store';
  import type { Market, Level } from '../lib/types';
  import { px, pct, probColor, lean, HORIZON_MIN, usd, biasWord, biasShort, conviction, dirOf } from '../lib/format';
  import Roll from './Roll.svelte';
  import { safe, report } from '../lib/report';
  export let sym: string;
  let el: HTMLDivElement, cv: HTMLCanvasElement, el2: HTMLDivElement, cv2: HTMLCanvasElement;
  let chart2: IChartApi;                   // lower panel: big trades and volume, kept in step with the price chart
  let chart: IChartApi, candles: ISeriesApi<'Candlestick'>, buyV: ISeriesApi<'Histogram'>, sellV: ISeriesApi<'Histogram'>,
    bigS: ISeriesApi<'Histogram'>, scaleS: ISeriesApi<'Line'>;
  let cone: ISeriesApi<'Line'>[] = [];
  let plines: IPriceLine[] = [];
  let tf = 1;
  const FULL = { arrow: true, levels: true, zones: true, book: true, trades: true, cone: true, compact: false };
  const CLEAN = { arrow: true, levels: true, zones: true, book: true, trades: true, cone: false, compact: true };
  let show = { ...CLEAN };
  try { const v = localStorage.getItem('xahoo.chart2'); if (v) show = { ...CLEAN, ...JSON.parse(v) }; } catch { /* private mode */ }
  $: try { localStorage.setItem('xahoo.chart2', JSON.stringify(show)); } catch { /* ignore */ }
  $: preset = JSON.stringify(show) === JSON.stringify(CLEAN) ? 'clean' : JSON.stringify(show) === JSON.stringify(FULL) ? 'full' : '';
  let last: { time: number; open: number; high: number; low: number; close: number } | null = null;
  let timer: ReturnType<typeof setInterval>, raf = 0;
  $: m = $markets[sym] as Market;
  $: fc = m?.forecast?.h || {};
  $: lv = m?.forecast?.levels;
  $: chg = m?.price != null && m?.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null;
  const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  // vertical layout of the chart pane (fractions of its height)
  const PRICE_BOTTOM = 0.96;               // price chart now uses its whole pane
  const STRIP_H = 190;                      // px height of the lower panel (incl. its time axis)

  // live totals for the flow column
  const share60 = tweened(0.5, { duration: 600, easing: cubicOut });
  const share15 = tweened(0.5, { duration: 600, easing: cubicOut });
  const shareBook = tweened(0.5, { duration: 600, easing: cubicOut });
  $: share60.set(m && m.b60 + m.s60 > 0 ? m.b60 / (m.b60 + m.s60) : 0.5);
  $: share15.set(m && m.big15 && m.big15[0] + m.big15[1] > 0 ? m.big15[0] / (m.big15[0] + m.big15[1]) : 0.5);
  $: shareBook.set(m?.book?.['imb_0.25'] ?? 0.5);

  const FUTURE_BARS = 24;                 // minimum empty space right of the live candle (room for the direction line)
  const flowWidth = (plotW: number) => (show.zones || show.book ? Math.min(190, plotW * 0.17) : 0);
  let scaleW = 78;                         // price-axis width, used to place the live totals box
  let loadedTf = 0, userMoved = false;
  let alive = true;
  let widthTimer: ReturnType<typeof setInterval>, lastW = 0;                        // false once this chart is closed (market switched): late replies are ignored
  function liveView() {
    const nb = candles.data().length;
    // keep the buyers / sellers area clear of candles: leave that much empty space after the live candle
    const spacing = (chart.timeScale().options() as any).barSpacing || 6;
    const plotW = el.clientWidth - chart.priceScale('right').width();
    const fut = Math.max(FUTURE_BARS, Math.ceil((flowWidth(plotW) + 40) / spacing));
    chart.timeScale().setVisibleLogicalRange({ from: nb - 150, to: nb + fut });
    userMoved = false;
  }
  const volAt = new Map<number, { b: number; s: number }>();          // candle time -> taker buy / sell volume
  let candleLastT = 0, volLastT = 0;                                  // newest time in each series (update() needs >=)
  type Row = { time: number; open: number; high: number; low: number; close: number; v: number; tb: number };
  function rows(d: any): Row[] {
    const idx = (d?.t || []).map((_: number, i: number) => i).sort((a: number, b: number) => d.t[a] - d.t[b]);
    const out: Row[] = [];
    for (const i of idx) {
      const r = { time: +d.t[i], open: +d.o[i], high: +d.h[i], low: +d.l[i], close: +d.c[i], v: +d.v[i] || 0, tb: +d.tb[i] || 0 };
      if (![r.time, r.open, r.high, r.low, r.close].every(Number.isFinite)) continue;
      if (out.length && out[out.length - 1].time === r.time) out[out.length - 1] = r; else out.push(r);
    }
    return out;
  }
  function candleUpdate(bar: { time: number; open: number; high: number; low: number; close: number }) {
    if (bar.time < candleLastT || ![bar.open, bar.high, bar.low, bar.close].every(Number.isFinite)) return;
    candles.update({ ...bar, time: bar.time as any });
    candleLastT = bar.time;
  }
  function setVol(t: number, v: number, tb: number, full = false) {
    const b = tb, s = Math.max(v - tb, 0);
    volAt.set(t, { b, s });
    if (!full && t >= volLastT) {
      buyV.update({ time: t as any, value: b });
      sellV.update({ time: t as any, value: -s });
      volLastT = t;
    }
  }
  async function load() {
    try { await loadInner(); } catch (err) { report(err, `chart load ${sym} tf=${tf}`); }
  }
  async function loadInner() {
    if (loadedTf !== tf) {                  // first load or timeframe change: full history and the default view
      const want = tf;
      const d = rows(await api<any>(`/api/candles?sym=${sym}&tf=${want}&limit=500`));
      if (!alive || want !== tf) return;    // the user switched again while this was loading
      const data = d.map(r => ({ time: r.time as any, open: r.open, high: r.high, low: r.low, close: r.close }));
      candles.setData(data);
      volAt.clear();
      d.forEach(r => setVol(r.time, r.v, r.tb, true));
      buyV.setData(d.map(r => ({ time: r.time as any, value: r.tb })));
      sellV.setData(d.map(r => ({ time: r.time as any, value: -Math.max(r.v - r.tb, 0) })));
      candleLastT = volLastT = d.length ? d[d.length - 1].time : 0;
      last = d.length ? { time: d[d.length - 1].time, open: d[d.length - 1].open, high: d[d.length - 1].high, low: d[d.length - 1].low, close: d[d.length - 1].close } : null;
      candles.applyOptions({ priceFormat: { type: 'price', precision: m.digits, minMove: 1 / 10 ** m.digits } });
      loadedTf = tf;
      bigSig = ''; drawCone(); keepLevels(); liveView(); bigStrip();
      return;
    }
    // refresh: only the newest bars, applied with update() so zoom and scroll stay where the user left them
    const d = rows(await api<any>(`/api/candles?sym=${sym}&tf=${tf}&limit=3`));
    if (!alive || loadedTf !== tf) return;
    for (const r of d) {
      if (last && r.time < last.time) continue;
      const bar = { time: r.time, open: r.open, high: r.high, low: r.low, close: r.close };
      candleUpdate(bar);
      setVol(r.time, r.v, r.tb);
      last = { ...bar };
    }
    drawCone(); keepLevels();
  }
  const coneHs = () => (tf === 1 ? ['1m', '5m', '15m', '1h'] : tf === 5 ? ['5m', '15m', '1h', '4h'] : tf === 15 ? ['15m', '1h', '4h'] : ['1h', '4h', '1d']);
  const coneBars = () => HORIZON_MIN[coneHs()[coneHs().length - 1]] / tf;
  function drawCone() {
    if (!last || !m?.forecast || !show.cone) { cone.forEach(s => s.setData([])); return; }
    const ref = m.forecast.ref, hs = coneHs().filter(h => fc[h]);
    const knots = [{ t: 0, b68: 0, b95: 0 }, ...hs.map(h => ({ t: HORIZON_MIN[h], b68: fc[h].band68, b95: fc[h].band95 }))];
    const band = (mins: number, k: 'b68' | 'b95') => {
      for (let i = 1; i < knots.length; i++) if (mins <= knots[i].t) {
        const a = knots[i - 1], b = knots[i], w = (Math.sqrt(mins) - Math.sqrt(a.t)) / (Math.sqrt(b.t) - Math.sqrt(a.t));
        return a[k] + (b[k] - a[k]) * w;
      }
      return knots[knots.length - 1][k];
    };
    const n = Math.round(coneBars());
    const series: [number, 'b68' | 'b95', number][] = [[0, 'b95', 1], [1, 'b68', 1], [2, 'b68', -1], [3, 'b95', -1]];
    for (const [i, k, sign] of series) {
      const pts = [{ time: last.time as any, value: ref }];
      for (let j = 1; j <= n; j++) pts.push({ time: (last.time + j * tf * 60) as any, value: ref * Math.exp(sign * band(j * tf, k)) });
      cone[i].setData(pts);
    }
  }
  // support / resistance as solid price lines with an R1 / S1 tag on the price axis; thicker = more confluence
  function levelLines() {
    if (!candles) return;
    plines.forEach(l => candles.removePriceLine(l));
    plines = [];
    if (!show.levels || !lv) return;
    const add = (x: Level, col: string, tag: string) => plines.push(candles.createPriceLine({
      price: x.price, color: col, lineWidth: (x.strength >= 3 ? 3 : x.strength === 2 ? 2 : 1) as 1 | 2 | 3,
      lineStyle: LineStyle.Solid, axisLabelVisible: true, title: tag, lineVisible: true }));
    (lv.resistance || []).forEach((x, i) => add(x, css('--res'), `R${i + 1}`));
    (lv.support || []).forEach((x, i) => add(x, css('--sup'), `S${i + 1}`));
  }
  function keepLevels() {     // keep R1/S1 inside the price scale
    const keep = [lv?.resistance?.[0], lv?.support?.[0]].filter(Boolean) as Level[];
    if (last && scaleS) scaleS.setData(show.levels ? keep.map((x, i) => ({ time: (last!.time - (keep.length - 1 - i) * tf * 60) as any, value: x.price })) : []);
  }
  $: if (chart && m?.forecast) safe(() => { drawCone(); keepLevels(); levelLines(); }, 'forecast update');
  // big trades strip: one bar per candle, big buying minus big selling (USD)
  let bigSig = '';
  let hoverY: number | null = null, hoverT: number | null = null;
  let bigAt = new Map<number, { buy: number; sell: number }>();
  function bigStrip() {
    if (!bigS || !last) return;
    const per = new Map<number, number>();
    const bigs = new Map<number, { buy: number; sell: number }>();
    if (show.trades) for (const b of m?.big || []) {
      const t = Math.floor(b.ts / 1000 / (tf * 60)) * tf * 60;
      if (t > last.time) continue;
      per.set(t, (per.get(t) || 0) + (b.side === 'buy' ? b.usd : -b.usd));
      const g = bigs.get(t) || { buy: 0, sell: 0 }; g[b.side === 'buy' ? 'buy' : 'sell'] += b.usd; bigs.set(t, g);
    }
    bigAt = bigs;
    const list = [...per.entries()].sort((x, y) => x[0] - y[0]);
    const sig = list.map(([t, v]) => `${t}:${Math.round(v)}`).join(',');
    if (sig === bigSig) return;
    bigSig = sig;
    bigS.setData(list.map(([t, v]) => ({ time: t as any, value: v, color: v >= 0 ? 'rgba(46,230,168,.9)' : 'rgba(255,92,138,.9)' })));
  }
  $: if (candles && last) { m?.big; show.trades; tf; safe(bigStrip, 'big trades'); }
  // with big trades off, the volume bars use the whole lower panel
  $: if (chart2) { const on = show.trades; safe(() => chart2.priceScale('vol').applyOptions({ scaleMargins: on ? { top: 0.58, bottom: 0.02 } : { top: 0.14, bottom: 0.02 } }), 'volume panel'); }
  $: if (chart) { show; safe(() => { drawCone(); keepLevels(); levelLines(); }, 'layers'); }
  $: if (candles && last && m?.price != null) {
    // bucket by the SERVER clock (the viewer's clock may be off, and replay runs on a simulated clock)
    const bucket = Math.floor($serverTime / (tf * 60)) * tf * 60;
    if (bucket - last.time > tf * 60 * 2 || bucket < last.time) { /* out of step: the next refresh fixes it */ }
    else if (bucket > last.time) last = { time: bucket, open: last.close, high: Math.max(last.close, m.price), low: Math.min(last.close, m.price), close: m.price };
    else { last.high = Math.max(last.high, m.price); last.low = Math.min(last.low, m.price); last.close = m.price; }
    const bar = last;
    safe(() => candleUpdate(bar), 'live candle');
  }

  // ------------------------------------------------------------------ drawing helpers
  function pill(c: CanvasRenderingContext2D, x: number, y: number, text: string, col: string, align: 'left' | 'right' = 'left',
                bg = 'rgba(12,16,30,.9)', size = 11) {
    c.font = `600 ${size}px Inter, sans-serif`;
    const w = c.measureText(text).width + (size > 10 ? 14 : 10), h = size + 8;
    const x0 = align === 'left' ? x : x - w;
    c.fillStyle = bg; c.strokeStyle = col; c.lineWidth = 1;
    c.beginPath(); c.roundRect(x0, y - h / 2, w, h, 5); c.fill(); c.stroke();
    c.fillStyle = col; c.textBaseline = 'middle'; c.fillText(text, x0 + (size > 10 ? 7 : 5), y + 0.5);
    return w;
  }
  type Lbl = { y: number; y0: number; text: string; col: string; lane: 'l' | 'r'; short?: string };
  function layout(ls: Lbl[], gap: number, top: number, bottom: number) {
    for (const lane of ['l', 'r'] as const) {
      const xs = ls.filter(l => l.lane === lane).sort((a, b) => a.y - b.y);
      // clamp into the area first (edge pills start at the edge), then push apart downwards, keep the lowest
      // inside, push apart upwards, and finally push down again from the top so nothing overlaps at either edge
      xs.forEach(l => (l.y = Math.min(bottom, Math.max(top, l.y))));
      for (let i = 1; i < xs.length; i++) if (xs[i].y - xs[i - 1].y < gap) xs[i].y = xs[i - 1].y + gap;
      if (xs.length && xs[xs.length - 1].y > bottom) xs[xs.length - 1].y = bottom;
      for (let i = xs.length - 2; i >= 0; i--) if (xs[i].y > xs[i + 1].y - gap) xs[i].y = xs[i + 1].y - gap;
      if (xs.length && xs[0].y < top) xs[0].y = top;
      for (let i = 1; i < xs.length; i++) if (xs[i].y - xs[i - 1].y < gap) xs[i].y = xs[i - 1].y + gap;
    }
  }
  function canvas(cvs: HTMLCanvasElement) {
    const dpr = devicePixelRatio || 1, W = cvs.clientWidth, H = cvs.clientHeight;
    if (cvs.width !== Math.round(W * dpr) || cvs.height !== Math.round(H * dpr)) { cvs.width = Math.round(W * dpr); cvs.height = Math.round(H * dpr); }
    const c = cvs.getContext('2d')!;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    return { c, W, H };
  }

  function draw(t: number) {
    if (!alive) return;
    raf = requestAnimationFrame(draw);
    if (!chart || !cv || !m) return;
    safe(() => drawFrame(t), 'chart overlay');
  }
  function drawFrame(t: number) {
    const { c, W, H } = canvas(cv);
    const plotW = W - chart.priceScale('right').width(), plotH = H - chart.timeScale().height();
    const Y = (p: number) => candles.priceToCoordinate(p);
    const pulse = 0.5 + 0.5 * Math.sin(t / 380);
    const compact = !!show.compact;

    // ---- candle area
    c.save(); c.beginPath(); c.rect(0, 0, plotW, plotH); c.clip();
    const flowW = flowWidth(plotW);
    if (flowW) drawFlow(c, plotW, plotH, flowW, Y, pulse);
    const labels: Lbl[] = [];
    if (show.levels && lv) {
      const tol = lv.tol || 0.003;
      const all: [Level, string, string][] = [
        ...(lv.resistance || []).map((x, i) => [x, css('--res'), `R${i + 1}`] as [Level, string, string]),
        ...(lv.support || []).map((x, i) => [x, css('--sup'), `S${i + 1}`] as [Level, string, string])];
      for (const [x, col, tag] of all) {
        const y = Y(x.price);
        if (y == null) continue;
        if (m.price != null && Math.abs(Math.log(m.price / x.price)) < tol) {      // glow when price is near
          c.strokeStyle = col; c.globalAlpha = 0.25 + 0.45 * pulse; c.lineWidth = 7; c.shadowColor = col; c.shadowBlur = 14;
          c.beginPath(); c.moveTo(0, y); c.lineTo(plotW, y); c.stroke();
          c.shadowBlur = 0; c.globalAlpha = 1;
        }
        const r = x.reach?.[$fh] ?? x.reach?.['1h'];
        const rh = $fh in (x.reach || {}) ? $fh : '1h';
        labels.push({ y, y0: y, col, lane: 'l', text: `${tag}  ${px(x.price, m.digits)}  ${'●'.repeat(x.strength)}${'○'.repeat(3 - x.strength)}  ${r != null ? `reach ${rh} ${Math.round(r * 100)}%` : ''}`,
                      short: compact ? `${tag} · ${r != null ? `${Math.round(r * 100)}% reach ${rh}` : px(x.price, m.digits)}` : undefined });
      }
    }
    const near = (l: Lbl) => hoverY != null && Math.abs(hoverY - l.y0) < 10;
    const priceBottom = Math.min(plotH * PRICE_BOTTOM + 10, plotH - 14);      // keep edge pills fully visible
    // levels above / below the visible chart: one small pill per side instead of a stack
    for (const [side, test, y] of [['↑', (l: Lbl) => l.y0 < 0, 12], ['↓', (l: Lbl) => l.y0 > priceBottom, priceBottom]] as const) {
      const off = labels.filter(test);
      if (off.length > 1) {
        const txt = `${side} ` + off.map(l => (l.short || l.text).split(' · ')[0] + (l.short?.match(/(\d+)% reach/) ? ` ${l.short.match(/(\d+)% reach/)![1]}%` : '')).join(' · ');
        for (const l of off) labels.splice(labels.indexOf(l), 1);
        labels.push({ y: side === '↑' ? -1 : priceBottom + 1, y0: side === '↑' ? -1 : priceBottom + 1, col: off[0].col, lane: 'l', text: txt.slice(2), short: txt.slice(2) });
      }
    }
    layout(labels, 22, 12, priceBottom);
    for (const l of labels) {
      const body = l.short && !near(l) ? l.short : l.text;
      pill(c, 10, l.y, l.y0 < 0 ? `↑ ${body}` : l.y0 > priceBottom ? `↓ ${body}` : body, l.col);
    }
    if (hoverT != null) {                    // candle under the cursor
      const g = bigAt.get(hoverT), v = volAt.get(hoverT);
      const parts = [`${new Date(hoverT * 1000).toISOString().slice(11, 16)} UTC`];
      const q = (x: number) => x.toLocaleString('en-US', { maximumFractionDigits: x > 100 ? 0 : 2 });
      if (v) parts.push(`buyers ${q(v.b)} · sellers ${q(v.s)} ${m.short}`);
      parts.push(g ? `big trades: buy $${usd(g.buy).slice(2)} · sell $${usd(g.sell).slice(2)}` : 'no big trades');
      pill(c, 10, 64, parts.join('   ·   '), 'rgba(152,163,192,.9)', 'left', 'rgba(10,13,24,.92)');
    }
    c.restore();
    drawStrips();
  }

  function drawStrips() {
    if (!cv2 || !chart2) return;
    const { c } = canvas(cv2);
    const ph = el2.clientHeight - chart2.timeScale().height(), pw = el2.clientWidth - chart2.priceScale('right').width();
    c.font = '700 9px Inter, sans-serif'; c.textBaseline = 'top'; c.fillStyle = 'rgba(152,163,192,.7)';
    if (show.trades) {
      c.fillText(`BIG TRADES · NET BUY − SELL PER CANDLE (TRADES ≥ $${usd($bigUsd[sym] || 0).slice(2)})`, 10, 6);
      c.strokeStyle = 'rgba(148,163,214,.12)'; c.lineWidth = 1;
      c.beginPath(); c.moveTo(0, Math.round(ph * 0.5) + 0.5); c.lineTo(pw, Math.round(ph * 0.5) + 0.5); c.stroke();
    }
    c.fillText('VOLUME PER CANDLE · BUYERS ▲  SELLERS ▼', 10, show.trades ? ph * 0.5 + 4 : 6);
  }

  // ---- buyers / sellers area at the right edge of the price chart (24h volume by price, zones, book walls)
  function drawFlow(c: CanvasRenderingContext2D, plotW: number, plotH: number, W: number, Y: (p: number) => number | null, pulse: number) {
    const bottom = plotH * PRICE_BOTTOM + 6, mid = W / 2, half = mid - 4;
    c.save(); c.translate(plotW - W, 0);
    c.beginPath(); c.rect(0, 0, W, bottom); c.clip();
    const bgr = c.createLinearGradient(0, 0, W, 0);
    bgr.addColorStop(0, 'rgba(10,13,24,0)'); bgr.addColorStop(0.15, 'rgba(10,13,24,.45)'); bgr.addColorStop(1, 'rgba(10,13,24,.55)');
    c.fillStyle = bgr; c.fillRect(0, 0, W, bottom);
    // centre line and price marker
    c.strokeStyle = 'rgba(148,163,214,.14)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(mid + 0.5, 0); c.lineTo(mid + 0.5, bottom); c.stroke();
    const labels: Lbl[] = [];
    const pr = m.forecast?.profile;
    if (show.zones && pr && pr.buy?.length) {
      const n = pr.buy.length, bw = (pr.hi - pr.lo) / n;
      const mx = Math.max(...pr.buy, ...pr.sell) || 1;
      const zb = new Set(pr.zones.buyers.map(z => Math.min(n - 1, Math.floor((z.price - pr.lo) / bw))));
      const zs = new Set(pr.zones.sellers.map(z => Math.min(n - 1, Math.floor((z.price - pr.lo) / bw))));
      for (let i = 0; i < n; i++) {
        const y1 = Y(pr.lo + (i + 1) * bw), y0 = Y(pr.lo + i * bw);
        if (y1 == null || y0 == null) continue;
        const h = Math.max(1, y0 - y1 - 1);
        const lb = (pr.buy[i] / mx) * half, ls = (pr.sell[i] / mx) * half;
        c.fillStyle = `rgba(255,92,138,${zs.has(i) ? 0.85 : 0.32})`; c.fillRect(mid - ls, y1, ls, h);
        c.fillStyle = `rgba(46,230,168,${zb.has(i) ? 0.85 : 0.32})`; c.fillRect(mid + 1, y1, lb, h);
      }
      for (const z of pr.zones.sellers) { const y = Y(z.price); if (y != null) labels.push({ y, y0: y, lane: 'l', col: '#ff5c8a', text: `SELLERS ${usd(z.net).replace('−', '-').slice(1)}` }); }
      for (const z of pr.zones.buyers) { const y = Y(z.price); if (y != null) labels.push({ y, y0: y, lane: 'r', col: '#2ee6a8', text: `BUYERS ${usd(z.net).slice(1)}` }); }
    }
    const bk = m.book;
    if (show.book && bk) {
      for (const [walls, col, lane, name] of [[bk.ask, '#ff5c8a', 'l', 'ASK'], [bk.bid, '#2ee6a8', 'r', 'BID']] as const) {
        for (const w of walls) {
          const y = Y(w.price); if (y == null) continue;
          c.globalAlpha = 0.65 + 0.35 * pulse; c.fillStyle = col; c.shadowColor = col; c.shadowBlur = 10 * pulse;
          c.fillRect(lane === 'l' ? 0 : mid + 1, y - 1.5, lane === 'l' ? mid - 1 : mid - 1, 3);
          c.shadowBlur = 0; c.globalAlpha = 1;
          labels.push({ y, y0: y, lane, col, text: `${name} $${usd(w.usd).slice(2)}${w.age != null ? ` ${w.age < 60 ? w.age + 's' : Math.round(w.age / 60) + 'm'}` : ''}` });
        }
      }
    }
    if (m.price != null) {
      const y = Y(m.price);
      if (y != null) { c.strokeStyle = 'rgba(232,236,246,.75)'; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); c.setLineDash([]); }
    }
    // say what is still loading instead of leaving the column blank (profile comes with the first forecast,
    // the order book with the first snapshot a few seconds after start)
    const waiting = [show.zones && !pr?.buy?.length ? 'Volume by price: loading…' : '', show.book && !bk ? 'Order book: loading…' : ''].filter(Boolean);
    c.font = '600 10px Inter, sans-serif'; c.fillStyle = 'rgba(152,163,192,.75)'; c.textBaseline = 'middle';
    waiting.forEach((w, i) => { const tw = c.measureText(w).width; c.fillText(w, Math.max(4, mid - tw / 2), 40 + i * 16); });
    for (let i = labels.length - 1; i >= 0; i--) if (labels[i].y0 < 4 || labels[i].y0 > bottom - 4) labels.splice(i, 1);
    layout(labels, 19, 28, bottom - 10);
    for (const l of labels) pill(c, l.lane === 'l' ? 3 : W - 3, l.y, l.text, l.col, l.lane === 'l' ? 'left' : 'right', 'rgba(10,13,24,.88)', 9.5);
    // header
    c.fillStyle = 'rgba(10,13,24,.8)'; c.fillRect(0, 0, W, 20);
    c.font = '700 9px Inter, sans-serif'; c.textBaseline = 'middle';
    c.fillStyle = '#ff5c8a'; c.fillText('◂ SELLERS', 4, 10);
    c.fillStyle = '#2ee6a8'; const tw = c.measureText('BUYERS ▸').width; c.fillText('BUYERS ▸', W - tw - 4, 10);
    c.restore();
  }

  onMount(() => {
    chart = createChart(el, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontFamily: css('--mono'), fontSize: 11, attributionLogo: false } as any,
      grid: { vertLines: { color: 'rgba(148,163,214,.05)' }, horzLines: { color: 'rgba(148,163,214,.05)' } },
      rightPriceScale: { borderColor: 'rgba(148,163,214,.15)', scaleMargins: { top: 0.06, bottom: 0.06 }, minimumWidth: 78 },
      timeScale: { borderColor: 'rgba(148,163,214,.15)', timeVisible: true, secondsVisible: false, rightOffset: 8, visible: false },
      crosshair: { mode: 0, vertLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' }, horzLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' } },
    });
    candles = chart.addCandlestickSeries({ upColor: css('--up'), downColor: css('--down'), wickUpColor: css('--up'), wickDownColor: css('--down'), borderVisible: false });
    chart2 = createChart(el2, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontFamily: css('--mono'), fontSize: 10 },
      grid: { vertLines: { color: 'rgba(148,163,214,.05)' }, horzLines: { visible: false } },
      rightPriceScale: { borderColor: 'rgba(148,163,214,.15)', scaleMargins: { top: 0.1, bottom: 0.55 }, minimumWidth: 78 },
      timeScale: { borderColor: 'rgba(148,163,214,.15)', timeVisible: true, secondsVisible: false, rightOffset: 8 },
      crosshair: { mode: 0, vertLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' }, horzLine: { visible: false, labelVisible: false } },
      handleScroll: true, handleScale: true,
    });
    // big trades on the visible right scale (in $), volume on its own hidden scale in the lower half
    bigS = chart2.addHistogramSeries({ priceScaleId: 'big', priceLineVisible: false, lastValueVisible: false, base: 0 });
    chart2.priceScale('big').applyOptions({ scaleMargins: { top: 0.12, bottom: 0.56 }, visible: false });
    buyV = chart2.addHistogramSeries({ priceScaleId: 'vol', priceLineVisible: false, lastValueVisible: false, base: 0, color: 'rgba(46,230,168,.6)' });
    sellV = chart2.addHistogramSeries({ priceScaleId: 'vol', priceLineVisible: false, lastValueVisible: false, base: 0, color: 'rgba(255,92,138,.6)' });
    chart2.priceScale('vol').applyOptions({ scaleMargins: { top: 0.58, bottom: 0.02 }, visible: false });
    // keep both charts in step: scroll / zoom, crosshair, and the same price-axis width so the bars line up
    let syncing = false;
    chart.timeScale().subscribeVisibleLogicalRangeChange(r => { if (!r || syncing) return; syncing = true; chart2.timeScale().setVisibleLogicalRange(r); syncing = false; });
    chart2.timeScale().subscribeVisibleLogicalRangeChange(r => { if (!r || syncing) return; syncing = true; chart.timeScale().setVisibleLogicalRange(r); syncing = false; });
    chart2.subscribeCrosshairMove(prm => {
      hoverT = prm.time != null ? (prm.time as number) : null;
      if (prm.time != null) (chart as any).setCrosshairPosition?.(m?.price ?? 0, prm.time, candles); else (chart as any).clearCrosshairPosition?.();
    });
    widthTimer = setInterval(() => {
      if (!alive) return;
      const w = Math.max(chart.priceScale('right').width(), chart2.priceScale('right').width());
      if (w > 0 && w !== lastW) { lastW = w; scaleW = w; chart.applyOptions({ rightPriceScale: { minimumWidth: w } }); chart2.applyOptions({ rightPriceScale: { minimumWidth: w } }); }
    }, 1000);
    scaleS = chart.addLineSeries({ lineVisible: false, pointMarkersVisible: false, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    const mk = (color: string, style: LineStyle, w: 1 | 2) => chart.addLineSeries({ color, lineStyle: style, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });
    cone = [mk('rgba(139,124,255,.5)', LineStyle.Dotted, 1), mk('rgba(167,156,255,.95)', LineStyle.Dashed, 2), mk('rgba(167,156,255,.95)', LineStyle.Dashed, 2), mk('rgba(139,124,255,.5)', LineStyle.Dotted, 1)];
    load();
    timer = setInterval(load, 5000);           // the live candle's volume refreshes every 5 s
    chart.subscribeCrosshairMove(prm => {
      hoverY = prm.point ? prm.point.y : null; hoverT = prm.time != null ? (prm.time as number) : null;
      if (prm.time != null) (chart2 as any).setCrosshairPosition?.(0, prm.time, buyV); else (chart2 as any).clearCrosshairPosition?.();
    });
    chart.timeScale().subscribeVisibleLogicalRangeChange(r => { userMoved = !!r && r.to < candles.data().length - 1; });
    raf = requestAnimationFrame(draw);
  });
  onDestroy(() => { alive = false; clearInterval(timer); clearInterval(widthTimer); cancelAnimationFrame(raf); chart?.remove(); chart2?.remove(); });
  $: if (chart && sym) { tf; load(); }
  const toggles: [Exclude<keyof typeof show, 'compact' | 'arrow'>, string][] = [['levels', 'Support / resistance'], ['zones', 'Volume by price'], ['book', 'Order-book walls'], ['trades', 'Big trades'], ['cone', 'Expected range']];
  const f = (v: number) => `$${usd(v).slice(2)}`;
  // Big badge: the overall direction (5m, 15m, 1h, 4h combined) when the server sends one (coins). Metals have no
  // tested overall, so their badge follows the selected timeframe instead.
  $: head = m.forecast?.head ?? null;
  $: sel = fc[$fh];
  $: bp = head ? head.p : sel?.p ?? 0.5;
  $: blab = head ? head.lab : sel?.show ? dirOf(sel.p, sel.lab) : 0;
  $: bshow = !!head || !!sel?.show;
  $: dirKind = !bshow ? 'none' : blab === 0 ? 'flat' : blab > 0 ? 'up' : 'down';
  $: dirWord = { none: 'NO EDGE', flat: 'NEUTRAL', up: 'UP', down: 'DOWN' }[dirKind];
  $: bpct = blab === 0 ? `${(bp * 100).toFixed(1)}% up` : `${((bp >= 0.5 ? bp : 1 - bp) * 100).toFixed(1)}%`;
  $: bsub = head ? `${bpct} · next 1h` : sel?.show ? `${bpct} · ${$fh}` : $fh;
  $: btitle = head
    ? `Overall: 5m, 15m, 1h and 4h combined (probability shown for the next hour). ${head.agree} of ${head.of} timeframes lean this way.`
      + (head.skill?.shown_hit ? ` Tested 2024–26 on unseen data: when it leans (52%+) it was right ${(head.skill.shown_hit * 100).toFixed(1)}% of the time over the next hour` : '')
      + (head.skill?.agree_hit ? `; when all four timeframes agree, ${(head.skill.agree_hit * 100).toFixed(1)}%.` : '.')
      + ' A side shows from 2.5 points away from 50% and holds until the lean fades within 1.5 points.'
    : `Direction for the selected timeframe (${$fh}). A side shows from 2.5 points away from 50% and holds until the lean fades within 1.5 points.`;
</script>
<section class="fc panel">
  <header>
    {#key sym}<span class="lg" in:scale={{ duration: 420, start: 0.6, easing: backOut }}><CoinLogo {sym} short={m.short} size={46} /></span>{/key}
    <div class="nm"><div class="t">{m.name} <span>{m.sym} · USDⓈ-M perpetual futures</span></div>
      <div class="pr"><span class="num big"><Roll value={m.price} format={v => px(v, m.digits)} /></span>
        <span class="num chg" class:up={chg != null && chg >= 0} class:down={chg != null && chg < 0}>{pct(chg)} <em>24h</em></span></div></div>
    <div class="dirb {dirKind}" title={btitle}>
      <Arrow p={bp} lab={blab} show={bshow} size={34} />
      {#key dirKind + (head ? 'all' : $fh)}
        <div class="dw" in:fly={{ y: dirKind === 'down' ? -10 : 10, duration: 380, easing: cubicOut }}>
          <small>{head ? 'OVERALL · 5m–4h' : `${$fh} · no overall for metals`}</small>
          <b>{dirWord}</b><span class="num">{bsub}</span>
          {#if head}<span class="agr">{#each Object.entries(head.parts) as [h, q]}<i style="background:{probColor(q)}" title="{h}: {(q * 100).toFixed(1)}% up"></i>{/each}<em>{head.lab === 0 ? 'mixed' : `${head.agree}/${head.of} agree`}</em></span>{/if}
        </div>
        <i class="flash"></i>
      {/key}
    </div>
    <div class="hs">
      {#each Object.keys(HORIZON_MIN) as h}
        {@const x = fc[h]}
        <button class="hb" class:on={$fh === h} class:off={!x?.show} on:click={() => fh.set(h)}
          style={x?.show ? `--c:${probColor(x.p)}; --w:${Math.abs(lean(x.p)) * 50}%; --l:${x.p >= 0.5 ? '50%' : `calc(50% - ${Math.abs(lean(x.p)) * 50}%)`}` : ''}>
          <span class="hh num">{h}{#if x?.show}<b class="ls" class:long={dirOf(x.p, x.lab) > 0} class:neutral={dirOf(x.p, x.lab) === 0} class:slight={conviction(x.p) < 2}
            title={biasWord(x.p, x.lab)}>{biasShort(x.p, x.lab)}</b>{/if}</span>
          <span class="hv num"><Arrow p={x?.p ?? 0.5} lab={x?.lab} show={!!x?.show} size={22} />{x?.show ? `${((x.p >= 0.5 ? x.p : 1 - x.p) * 100).toFixed(1)}%` : 'no edge'}</span>
          <span class="hbar"><i></i></span>
        </button>
      {/each}
    </div>
  </header>
  <div class="bar">
    <span class="seg">{#each [[1, '1m'], [5, '5m'], [15, '15m'], [60, '1h']] as [v, l]}<button class:on={tf === v} on:click={() => (tf = +v)}>{l}</button>{/each}</span>
    <span class="seg pre"><button class:on={preset === 'clean'} on:click={() => (show = { ...CLEAN })} title="Short level tags (full on hover), no expected-range cone">Clean</button><button class:on={preset === 'full'} on:click={() => (show = { ...FULL })}>Full</button></span>
    <span class="tg">{#each toggles as [k, l]}<button class="chipb" class:act={show[k]} on:click={() => (show[k] = !show[k])}><i class="sw {k}"></i>{l}</button>{/each}</span>
    {#if userMoved}<button class="live" on:click={liveView} title="Return to the live edge">⟲ Back to live</button>{/if}
    {#if m.book?.sim}<span class="simtag" title="Replay mode: the archive has no order book or single trades, so these are simulated">SIMULATED BOOK &amp; TRADES</span>{/if}
  </div>
  <div class="area">
    <div class="charts">
      <div class="chart" bind:this={el}><canvas bind:this={cv}></canvas></div>
      <div class="strips" bind:this={el2} style="height:{STRIP_H}px"><canvas bind:this={cv2}></canvas>
      <div class="totals" style="right:{scaleW}px">
        <div class="lt">Live · last 60 s</div>
        <div class="row"><b class="up num">{f(m.b60)}</b><b class="down num">{f(m.s60)}</b></div>
        <div class="split"><i style="width:{$share60 * 100}%"></i></div>
        <div class="lt">Big trades · 15 min</div>
        <div class="row"><b class="up num">{f(m.big15?.[0] || 0)}</b><b class="down num">{f(m.big15?.[1] || 0)}</b></div>
        <div class="split"><i style="width:{$share15 * 100}%"></i></div>
        <div class="lt">Order book ±0.25%</div>
        <div class="row"><b class="up num">{m.book?.['imb_0.25'] != null ? `${Math.round(m.book['imb_0.25'] * 100)}% bids` : '—'}</b><b class="down num">{m.book?.['imb_0.25'] != null ? `${100 - Math.round(m.book['imb_0.25'] * 100)}% asks` : ''}</b></div>
        <div class="split"><i style="width:{$shareBook * 100}%"></i></div>
      </div>
      </div>
    </div>
  </div>
  <div class="foot"><span><i class="k z"></i>chart right edge: 24h volume by price (sellers ◂ ▸ buyers), buyer / seller zones, order-book walls</span><span><i class="k d"></i>lower panel: big trades and volume per candle, live buy / sell totals</span><span>hover the chart for details</span></div>
</section>
<style>
  .fc { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  header { display: flex; align-items: center; gap: 14px; padding: 14px 18px 10px; flex-wrap: wrap; }
  .nm { min-width: 0; flex: 0 1 auto; }
  .lg { display: inline-flex; flex: none; }
  .hv:has(> :global(.off)) { font-size: 12px; font-weight: 600; }
  .t { font: 700 16px var(--sans); } .t span { font-weight: 500; font-size: 11.5px; color: var(--faint); margin-left: 6px; }
  .pr { display: flex; align-items: baseline; gap: 12px; }
  .big { font-size: 30px; font-weight: 700; letter-spacing: -1px; line-height: 1.1; }
  .chg { font-size: 13px; } .chg em { font-style: normal; font-size: 10px; color: var(--faint); font-family: var(--sans); }
  .dirb { position: relative; display: flex; align-items: center; gap: 10px; padding: 8px 14px 8px 10px; border-radius: 14px; border: 1.5px solid var(--line2); background: rgba(148,163,214,.06); transition: all .4s; overflow: hidden; }
  .dw { min-width: 112px; display: flex; flex-direction: column; gap: 2px; }
  .dw small { font: 700 9px var(--sans); letter-spacing: 1.2px; color: var(--faint); }
  .agr { display: flex; align-items: center; gap: 3px; margin-top: 1px; }
  .agr i { width: 14px; height: 4px; border-radius: 2px; background: var(--line2); transition: background .5s; }
  .agr em { font: 600 10px var(--sans); font-style: normal; color: var(--muted); margin-left: 4px; }
  .flash { position: absolute; inset: -2px; border-radius: 14px; pointer-events: none; animation: dflash 1s ease-out forwards; }
  .dirb.up .flash { box-shadow: inset 0 0 0 2px var(--up), inset 0 0 24px rgba(var(--up-rgb), .45); }
  .dirb.down .flash { box-shadow: inset 0 0 0 2px var(--down), inset 0 0 24px rgba(var(--down-rgb), .45); }
  .dirb.flat .flash, .dirb.none .flash { box-shadow: inset 0 0 0 2px rgba(148,163,214,.5); }
  @keyframes dflash { from { opacity: 1; } to { opacity: 0; } }
  .dirb b { display: block; font: 900 20px/1 var(--sans); letter-spacing: 2px; }
  .dirb span { font-size: 12px; color: var(--muted); }
  .dirb.up { border-color: rgba(var(--up-rgb), .7); background: rgba(var(--up-rgb), .12); } .dirb.up b { color: var(--up); }
  .dirb.down { border-color: rgba(var(--down-rgb), .7); background: rgba(var(--down-rgb), .12); } .dirb.down b { color: var(--down); }
  .dirb.flat b, .dirb.none b { color: var(--muted); }
  .hs { margin-left: auto; display: grid; grid-template-columns: repeat(6, minmax(74px, 1fr)); gap: 6px; flex: 1 1 480px; min-width: 0; max-width: 760px; }
  @media (max-width: 900px) { .hs { grid-template-columns: repeat(3, 1fr); min-width: 100%; } .big { font-size: 24px; } .hv { font-size: 14px; } }
  .hb { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; padding: 8px 9px; min-width: 0; border-radius: 11px; background: rgba(148,163,214,.04); text-align: left; }
  .hb.on { background: rgba(139,124,255,.14); border-color: var(--accent); box-shadow: 0 0 0 1px rgba(139,124,255,.3), 0 8px 24px rgba(139,124,255,.15); }
  .hh { font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; gap: 4px; width: 100%; }
  .ls { font: 800 8.5px var(--sans); letter-spacing: .6px; color: var(--down); } .ls.long { color: var(--up); } .ls.slight { opacity: .6; } .ls.neutral { color: var(--faint); }
  .hv { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; font-size: clamp(13px, 0.9vw, 17px); font-weight: 700; color: var(--c, var(--faint)); transition: color .6s; }
  .hb.off .hv { font: 500 12px var(--sans); }
  .hbar { position: relative; width: 100%; height: 4px; border-radius: 2px; background: rgba(148,163,214,.1); }
  .hbar i { position: absolute; top: 0; bottom: 0; left: var(--l, 50%); width: var(--w, 0); background: var(--c); border-radius: 2px; transition: all .7s ease; box-shadow: 0 0 8px var(--c); }
  .bar { display: flex; align-items: center; gap: 14px; padding: 0 18px 8px; flex-wrap: wrap; }
  .seg { display: inline-flex; gap: 4px; } .seg button { padding: 3px 11px; font-size: 11px; }
  .pre button { border-radius: 99px; }
  .tg { display: inline-flex; gap: 6px; flex-wrap: wrap; }
  .chipb { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; font-size: 11px; border-radius: 99px; opacity: .55; }
  .chipb.act { opacity: 1; color: var(--text); }
  .sw { width: 10px; height: 10px; border-radius: 3px; }
  .sw.levels { height: 0; border-radius: 0; border-top: 3px solid var(--res); box-shadow: 0 5px 0 -1px var(--sup); }
  .sw.zones { background: linear-gradient(90deg, var(--down) 0 45%, transparent 45% 55%, var(--up) 55%); }
  .sw.book { background: var(--up); box-shadow: 0 0 6px var(--up); height: 3px; }
  .sw.trades { border-radius: 1px; background: linear-gradient(90deg, var(--up) 0 30%, transparent 30% 70%, var(--down) 70%); } .sw.cone { background: #a79cff; }
  .sw.arrow { width: 14px; height: 0; border-radius: 0; border-top: 3px solid var(--up); position: relative; }
  .sw.arrow::after { content: ""; position: absolute; right: -3px; top: -6px; border-left: 6px solid var(--up); border-top: 4.5px solid transparent; border-bottom: 4.5px solid transparent; }
  .bar > .live { margin-left: auto; border-radius: 99px; color: var(--text); border-color: var(--accent); background: rgba(139,124,255,.15); font-weight: 600; animation: pop .3s ease-out; }
  @keyframes pop { from { transform: scale(.85); opacity: 0; } to { transform: none; opacity: 1; } }
  .simtag { margin-left: auto; font: 700 9.5px var(--sans); letter-spacing: 1.2px; color: var(--res); border: 1px dashed var(--res); padding: 2px 8px; border-radius: 6px; }
  .area { flex: 1; min-height: 480px; display: flex; margin: 0 10px 0 12px; }
  .charts { flex: 1; }
  .charts { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .charts .chart { flex: 1; min-height: 260px; }
  .strips { position: relative; flex: none; border-top: 1px solid rgba(148,163,214,.16); background: rgba(10,13,24,.25); }
  .strips canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 3; }
  .chart { position: relative; min-width: 0; }
  .chart canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 3; }
  .totals { position: absolute; top: 0; bottom: 28px; width: 190px; padding: 8px 10px 4px; display: flex; flex-direction: column; gap: 2px;
    background: linear-gradient(90deg, rgba(10,13,24,0), rgba(10,13,24,.75) 18%); z-index: 4; pointer-events: none; }
  .lt { font: 700 9px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); margin-top: 3px; }
  .row { display: flex; justify-content: space-between; font-size: 11.5px; }
  .split { position: relative; height: 5px; border-radius: 3px; background: rgba(255,92,138,.75); overflow: hidden; }
  .split i { position: absolute; left: 0; top: 0; bottom: 0; background: var(--up); }
  .split::after { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: rgba(255,255,255,.7); }
  .foot { display: flex; gap: 20px; padding: 6px 18px 10px; font-size: 10.5px; color: var(--faint); flex-wrap: wrap; }
  .k { display: inline-block; width: 10px; height: 8px; margin-right: 6px; border-radius: 2px; vertical-align: 0; }
  .k.d { background: linear-gradient(90deg, var(--up) 50%, var(--down) 50%); } .k.z { background: linear-gradient(90deg, rgba(255,92,138,.6) 50%, rgba(46,230,168,.6) 50%); }
  @media (max-width: 900px) { .totals { display: none; } }
</style>
