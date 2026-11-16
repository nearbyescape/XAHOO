<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createChart, type IChartApi, type ISeriesApi, LineStyle } from 'lightweight-charts';
  import { api, markets, fh, bigUsd, now, serverTime } from '../lib/store';
  import type { Market, Level } from '../lib/types';
  import { px, pct, probColor, lean, HORIZON_MIN, BADGE, usd } from '../lib/format';
  import Roll from './Roll.svelte';
  export let sym: string;
  let wrap: HTMLElement, el: HTMLDivElement, cv: HTMLCanvasElement;
  let chart: IChartApi, candles: ISeriesApi<'Candlestick'>, delta: ISeriesApi<'Histogram'>, scaleS: ISeriesApi<'Line'>;
  let cone: ISeriesApi<'Line'>[] = [];
  let tf = 1;
  let show = { levels: true, zones: true, book: true, trades: true, cone: true };
  let last: { time: number; open: number; high: number; low: number; close: number } | null = null;
  let timer: ReturnType<typeof setInterval>, raf = 0;
  $: m = $markets[sym] as Market;
  $: fc = m?.forecast?.h || {};
  $: lv = m?.forecast?.levels;
  $: badge = BADGE[sym] || ['#8b7cff', '#38c6f4'];
  $: chg = m?.price != null && m?.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null;
  const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  async function load() {
    const d = await api<any>(`/api/candles?sym=${sym}&tf=${tf}&limit=500`);
    const data = d.t.map((t: number, i: number) => ({ time: t, open: d.o[i], high: d.h[i], low: d.l[i], close: d.c[i] }));
    candles.setData(data);
    delta.setData(d.t.map((t: number, i: number) => {
      const v = 2 * d.tb[i] - d.v[i];
      return { time: t, value: v, color: v >= 0 ? 'rgba(46,230,168,.55)' : 'rgba(255,92,138,.55)' };
    }));
    last = data.length ? { ...data[data.length - 1] } : null;
    candles.applyOptions({ priceFormat: { type: 'price', precision: m.digits, minMove: 1 / 10 ** m.digits } });
    drawCone(); keepLevels();
    chart.timeScale().setVisibleLogicalRange({ from: data.length - 160, to: data.length + coneBars() + 6 });
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
  function keepLevels() {     // keep R1/S1 inside the price scale
    const keep = [lv?.resistance?.[0], lv?.support?.[0]].filter(Boolean) as Level[];
    if (last && scaleS) scaleS.setData(show.levels ? keep.map((x, i) => ({ time: (last!.time - (keep.length - 1 - i) * tf * 60) as any, value: x.price })) : []);
  }
  $: if (chart && m?.forecast) { drawCone(); keepLevels(); }
  $: if (chart) { show; drawCone(); keepLevels(); }
  $: if (candles && last && m?.price != null) {
    // bucket by the SERVER clock (the viewer's clock may be off, and replay runs on a simulated clock)
    const bucket = Math.floor($serverTime / (tf * 60)) * tf * 60;
    if (bucket - last.time > tf * 60 * 2 || bucket < last.time) { /* out of step: the next reload fixes it */ }
    else if (bucket > last.time) last = { time: bucket, open: last.close, high: Math.max(last.close, m.price), low: Math.min(last.close, m.price), close: m.price };
    else { last.high = Math.max(last.high, m.price); last.low = Math.min(last.low, m.price); last.close = m.price; }
    candles.update({ ...last, time: last.time as any });
  }

  // ------------------------------------------------------------------ overlay
  function pill(c: CanvasRenderingContext2D, x: number, y: number, text: string, col: string, align: 'left' | 'right' = 'left', bg = 'rgba(12,16,30,.88)') {
    c.font = '600 11px Inter, sans-serif';
    const w = c.measureText(text).width + 14, h = 19;
    const x0 = align === 'left' ? x : x - w;
    c.fillStyle = bg; c.strokeStyle = col; c.lineWidth = 1;
    c.beginPath(); c.roundRect(x0, y - h / 2, w, h, 6); c.fill(); c.stroke();
    c.fillStyle = col; c.textBaseline = 'middle'; c.fillText(text, x0 + 7, y + 0.5);
    return w;
  }
  type Lbl = { y: number; y0: number; text: string; col: string; lane: 'l' | 'r' };
  function layout(ls: Lbl[], gap = 22, top = 12, bottom = 1e9) {
    for (const lane of ['l', 'r'] as const) {
      const xs = ls.filter(l => l.lane === lane).sort((a, b) => a.y - b.y);
      for (let i = 1; i < xs.length; i++) if (xs[i].y - xs[i - 1].y < gap) xs[i].y = xs[i - 1].y + gap;
      for (let i = xs.length - 2; i >= 0; i--) if (xs[i].y > xs[i + 1].y - gap) xs[i].y = xs[i + 1].y - gap;
      xs.forEach(l => (l.y = Math.max(top, Math.min(bottom, l.y))));
    }
  }
  function draw(t: number) {
    raf = requestAnimationFrame(draw);
    if (!chart || !cv || !m) return;
    const dpr = devicePixelRatio || 1, W = el.clientWidth, H = el.clientHeight;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    const c = cv.getContext('2d')!;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const plotW = W - chart.priceScale('right').width(), plotH = H - chart.timeScale().height();
    c.save(); c.beginPath(); c.rect(0, 0, plotW, plotH); c.clip();
    const Y = (p: number) => candles.priceToCoordinate(p);
    const pulse = 0.5 + 0.5 * Math.sin(t / 380);
    const RES = css('--res'), SUP = css('--sup');
    const profW = Math.min(170, plotW * 0.16);
    const labels: Lbl[] = [];

    // buyer / seller volume by price (last 24 h), right edge
    const pr = m.forecast?.profile;
    if (show.zones && pr && pr.buy?.length) {
      const n = pr.buy.length, bw = (pr.hi - pr.lo) / n;
      const mx = Math.max(...pr.buy.map((b, i) => b + pr.sell[i])) || 1;
      const zb = new Set(pr.zones.buyers.map(z => Math.min(n - 1, Math.floor((z.price - pr.lo) / bw))));
      const zs = new Set(pr.zones.sellers.map(z => Math.min(n - 1, Math.floor((z.price - pr.lo) / bw))));
      for (let i = 0; i < n; i++) {
        const y1 = Y(pr.lo + (i + 1) * bw), y0 = Y(pr.lo + i * bw);
        if (y1 == null || y0 == null) continue;
        const h = Math.max(1, y0 - y1 - 1), lb = (pr.buy[i] / mx) * profW, ls = (pr.sell[i] / mx) * profW;
        const hot = zb.has(i) || zs.has(i);
        c.fillStyle = `rgba(46,230,168,${hot && zb.has(i) ? 0.75 : 0.22})`; c.fillRect(plotW - lb, y1, lb, h);
        c.fillStyle = `rgba(255,92,138,${hot && zs.has(i) ? 0.75 : 0.22})`; c.fillRect(plotW - lb - ls, y1, ls, h);
      }
      for (const [zones, col, name] of [[pr.zones.buyers, '#2ee6a8', 'BUYERS'], [pr.zones.sellers, '#ff5c8a', 'SELLERS']] as const) {
        for (const z of zones) {
          const y = Y(z.price); if (y == null) continue;
          labels.push({ y, y0: y, text: `${name} ${usd(z.net)} net · 24h`, col, lane: 'r' });
        }
      }
    }
    // support / resistance zones
    if (show.levels && lv) {
      const tol = lv.tol || 0.003;
      const all: [Level, string, string][] = [
        ...(lv.resistance || []).map((x, i) => [x, RES, `R${i + 1}`] as [Level, string, string]),
        ...(lv.support || []).map((x, i) => [x, SUP, `S${i + 1}`] as [Level, string, string])];
      for (const [x, col, tag] of all) {
        const y = Y(x.price), ya = Y(x.price * (1 + tol / 2)), yb = Y(x.price * (1 - tol / 2));
        if (y == null || ya == null || yb == null) continue;
        const near = m.price != null && Math.abs(Math.log(m.price / x.price)) < tol;
        const a = near ? 0.10 + 0.12 * pulse : 0.07 + 0.03 * x.strength;
        c.fillStyle = col.startsWith('#') ? col + Math.round(a * 255).toString(16).padStart(2, '0') : col;
        const yq = (ya + yb) / 2, hh = Math.max(3, (yb - ya) / 2);
        c.fillRect(0, yq - hh / 2, plotW, hh);
        c.strokeStyle = col; c.globalAlpha = 0.85; c.lineWidth = x.strength >= 3 ? 1.6 : 1;
        c.setLineDash(x.strength >= 2 ? [6, 4] : [2, 4]);
        c.beginPath(); c.moveTo(0, Math.round(y) + 0.5); c.lineTo(plotW, Math.round(y) + 0.5); c.stroke();
        c.setLineDash([]); c.globalAlpha = 1;
        const r = x.reach?.[$fh] ?? x.reach?.['1h'];
        labels.push({ y, y0: y, col, lane: 'l', text: `${tag}  ${px(x.price, m.digits)}  ${'●'.repeat(x.strength)}${'○'.repeat(3 - x.strength)}  ${r != null ? `reach ${$fh in (x.reach || {}) ? $fh : '1h'} ${Math.round(r * 100)}%` : ''}` });
      }
    }
    // order-book walls
    const bk = m.book;
    if (show.book && bk) {
      const mx = Math.max(1, ...bk.bid.map(w => w.usd), ...bk.ask.map(w => w.usd));
      for (const [walls, col, name] of [[bk.bid, '#2ee6a8', 'BID WALL'], [bk.ask, '#ff5c8a', 'ASK WALL']] as const) {
        for (const w of walls) {
          const y = Y(w.price); if (y == null) continue;
          const len = Math.max(14, profW * (w.usd / mx));
          c.strokeStyle = col; c.globalAlpha = 0.25; c.lineWidth = 1; c.setLineDash([1, 3]);
          c.beginPath(); c.moveTo(0, y); c.lineTo(plotW - profW, y); c.stroke(); c.setLineDash([]);
          c.globalAlpha = 0.7 + 0.3 * pulse; c.fillStyle = col;
          c.shadowColor = col; c.shadowBlur = 12 * pulse;
          c.fillRect(plotW - len, y - 2.5, len, 5);
          c.shadowBlur = 0; c.globalAlpha = 1;
          labels.push({ y, y0: y, col, lane: 'r', text: `${name} $${usd(w.usd).slice(2)}${w.age != null ? ` · ${w.age < 60 ? w.age + 's' : Math.round(w.age / 60) + 'm'}` : ''}` });
        }
      }
    }
    // labels, spread out so none overlap; a thin leader shows where a moved label belongs
    layout(labels, 22, 12, plotH - 12);
    for (const l of labels) {
      const x = l.lane === 'l' ? 10 : plotW - profW - 8;
      if (Math.abs(l.y - l.y0) > 2) {
        c.strokeStyle = l.col; c.globalAlpha = 0.6; c.lineWidth = 1;
        c.beginPath(); c.moveTo(l.lane === 'l' ? x + 4 : x - 4, l.y); c.lineTo(l.lane === 'l' ? x - 2 : x + 6, l.y0); c.stroke(); c.globalAlpha = 1;
      }
      const txt = l.y0 < 0 ? `↑ ${l.text}` : l.y0 > plotH ? `↓ ${l.text}` : l.text;      // level is off the visible chart
      pill(c, x, l.y, txt, l.col, l.lane === 'l' ? 'left' : 'right');
    }
    // big trades
    if (show.trades && m.big?.length) {
      const thr = $bigUsd[sym] || 1e5, nowMs = now() * 1000;
      for (const b of m.big) {
        const bucket = Math.floor(b.ts / 1000 / (tf * 60)) * tf * 60;
        const x = chart.timeScale().timeToCoordinate(bucket as any), y = Y(b.price);
        if (x == null || y == null) continue;
        const r = 4 + 5 * Math.sqrt(b.usd / thr);
        const col = b.side === 'buy' ? '46,230,168' : '255,92,138';
        const age = (nowMs - b.ts) / 1000;
        c.fillStyle = `rgba(${col},.35)`; c.strokeStyle = `rgba(${col},.95)`; c.lineWidth = 1.2;
        c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill(); c.stroke();
        if (age < 4) {                       // ripple on arrival
          const k = age / 4;
          c.strokeStyle = `rgba(${col},${1 - k})`; c.beginPath(); c.arc(x, y, r + 22 * k, 0, Math.PI * 2); c.stroke();
        }
      }
    }
    c.restore();
  }

  onMount(() => {
    chart = createChart(el, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontFamily: css('--mono'), fontSize: 11 },
      grid: { vertLines: { color: 'rgba(148,163,214,.05)' }, horzLines: { color: 'rgba(148,163,214,.05)' } },
      rightPriceScale: { borderColor: 'rgba(148,163,214,.15)', scaleMargins: { top: 0.06, bottom: 0.2 } },
      timeScale: { borderColor: 'rgba(148,163,214,.15)', timeVisible: true, secondsVisible: false, rightOffset: 8 },
      crosshair: { mode: 0, vertLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' }, horzLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' } },
    });
    candles = chart.addCandlestickSeries({ upColor: css('--up'), downColor: css('--down'), wickUpColor: css('--up'), wickDownColor: css('--down'), borderVisible: false });
    delta = chart.addHistogramSeries({ priceScaleId: 'delta', priceLineVisible: false, lastValueVisible: false, base: 0 });
    chart.priceScale('delta').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 }, visible: false });
    scaleS = chart.addLineSeries({ lineVisible: false, pointMarkersVisible: false, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    const mk = (color: string, style: LineStyle, w: 1 | 2) => chart.addLineSeries({ color, lineStyle: style, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });
    cone = [mk('rgba(139,124,255,.5)', LineStyle.Dotted, 1), mk('rgba(167,156,255,.95)', LineStyle.Dashed, 2), mk('rgba(167,156,255,.95)', LineStyle.Dashed, 2), mk('rgba(139,124,255,.5)', LineStyle.Dotted, 1)];
    load();
    timer = setInterval(load, 60000);
    raf = requestAnimationFrame(draw);
  });
  onDestroy(() => { clearInterval(timer); cancelAnimationFrame(raf); chart?.remove(); });
  $: if (chart && sym) { tf; load(); }
  const toggles: [keyof typeof show, string][] = [['levels', 'Support / resistance'], ['zones', 'Buyer / seller zones'], ['book', 'Order-book walls'], ['trades', 'Big trades'], ['cone', 'Expected range']];
</script>
<section class="fc panel" bind:this={wrap}>
  <header>
    <span class="badge" class:long={m.short.length > 3} style="background:linear-gradient(135deg, {badge[0]}, {badge[1]})">{m.short}</span>
    <div class="nm"><div class="t">{m.name} <span>{m.sym} · Binance perpetual</span></div>
      <div class="pr"><span class="num big"><Roll value={m.price} format={v => px(v, m.digits)} /></span>
        <span class="num chg" class:up={chg != null && chg >= 0} class:down={chg != null && chg < 0}>{pct(chg)} <em>24h</em></span></div></div>
    <div class="hs">
      {#each Object.keys(HORIZON_MIN) as h}
        {@const x = fc[h]}
        <button class="hb" class:on={$fh === h} class:off={!x?.show} on:click={() => fh.set(h)}
          style={x?.show ? `--c:${probColor(x.p)}; --w:${Math.abs(lean(x.p)) * 50}%; --l:${x.p >= 0.5 ? '50%' : `calc(50% - ${Math.abs(lean(x.p)) * 50}%)`}` : ''}>
          <span class="hh num">{h}</span>
          <span class="hv num">{x?.show ? `${x.p >= 0.5 ? '▲' : '▼'} ${((x.p >= 0.5 ? x.p : 1 - x.p) * 100).toFixed(1)}%` : 'no edge'}</span>
          <span class="hbar"><i></i></span>
        </button>
      {/each}
    </div>
  </header>
  <div class="bar">
    <span class="seg">{#each [[1, '1m'], [5, '5m'], [15, '15m'], [60, '1h']] as [v, l]}<button class:on={tf === v} on:click={() => (tf = +v)}>{l}</button>{/each}</span>
    <span class="tg">{#each toggles as [k, l]}<button class="chipb" class:act={show[k]} on:click={() => (show[k] = !show[k])}><i class="sw {k}"></i>{l}</button>{/each}</span>
    {#if m.book?.sim}<span class="simtag" title="Replay mode: the archive has no order book or single trades, so these are simulated">SIMULATED BOOK &amp; TRADES</span>{/if}
  </div>
  <div class="chart" bind:this={el}><canvas bind:this={cv}></canvas></div>
  <div class="foot"><span><i class="k d"></i>bars under candles: aggressive buy − sell volume</span><span><i class="k z"></i>right edge: 24h volume by price (buyers / sellers)</span><span><i class="k c"></i>dashed violet: 68% and 95% expected range</span></div>
</section>
<style>
  .fc { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  header { display: flex; align-items: center; gap: 16px; padding: 14px 18px 10px; flex-wrap: wrap; }
  .badge { width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center; font: 800 13px var(--sans); color: #0b0e1a; box-shadow: 0 6px 20px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.35); }
  .badge.long { font-size: 11px; }
  .t { font: 700 16px var(--sans); } .t span { font-weight: 500; font-size: 11.5px; color: var(--faint); margin-left: 6px; }
  .pr { display: flex; align-items: baseline; gap: 12px; }
  .big { font-size: 30px; font-weight: 700; letter-spacing: -1px; line-height: 1.1; }
  .chg { font-size: 13px; } .chg em { font-style: normal; font-size: 10px; color: var(--faint); font-family: var(--sans); }
  .hs { margin-left: auto; display: grid; grid-template-columns: repeat(6, minmax(92px, 1fr)); gap: 8px; flex: 1; max-width: 760px; }
  @media (max-width: 900px) { .hs { grid-template-columns: repeat(3, 1fr); min-width: 100%; } .big { font-size: 24px; } .hv { font-size: 14px; } }
  .hb { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; padding: 8px 11px; border-radius: 11px; background: rgba(148,163,214,.04); text-align: left; }
  .hb.on { background: rgba(139,124,255,.14); border-color: var(--accent); box-shadow: 0 0 0 1px rgba(139,124,255,.3), 0 8px 24px rgba(139,124,255,.15); }
  .hh { font-size: 11px; color: var(--muted); } .hv { font-size: 17px; font-weight: 700; color: var(--c, var(--faint)); transition: color .6s; }
  .hb.off .hv { font: 500 12px var(--sans); }
  .hbar { position: relative; width: 100%; height: 4px; border-radius: 2px; background: rgba(148,163,214,.1); }
  .hbar i { position: absolute; top: 0; bottom: 0; left: var(--l, 50%); width: var(--w, 0); background: var(--c); border-radius: 2px; transition: all .7s ease; box-shadow: 0 0 8px var(--c); }
  .bar { display: flex; align-items: center; gap: 14px; padding: 0 18px 8px; flex-wrap: wrap; }
  .seg { display: inline-flex; gap: 4px; } .seg button { padding: 3px 11px; font-size: 11px; }
  .tg { display: inline-flex; gap: 6px; flex-wrap: wrap; }
  .chipb { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; font-size: 11px; border-radius: 99px; opacity: .55; }
  .chipb.act { opacity: 1; color: var(--text); }
  .sw { width: 10px; height: 10px; border-radius: 3px; }
  .sw.levels { background: linear-gradient(135deg, var(--res) 50%, var(--sup) 50%); } .sw.zones { background: linear-gradient(135deg, var(--up) 50%, var(--down) 50%); }
  .sw.book { background: var(--up); box-shadow: 0 0 6px var(--up); } .sw.trades { border-radius: 50%; background: var(--down); } .sw.cone { background: #a79cff; }
  .simtag { margin-left: auto; font: 700 9.5px var(--sans); letter-spacing: 1.2px; color: var(--res); border: 1px dashed var(--res); padding: 2px 8px; border-radius: 6px; }
  .chart { position: relative; flex: 1; min-height: 360px; margin: 0 8px 0 12px; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 3; }
  .foot { display: flex; gap: 20px; padding: 6px 18px 10px; font-size: 10.5px; color: var(--faint); flex-wrap: wrap; }
  .k { display: inline-block; width: 10px; height: 8px; margin-right: 6px; border-radius: 2px; vertical-align: 0; }
  .k.d { background: linear-gradient(90deg, var(--up) 50%, var(--down) 50%); } .k.z { background: linear-gradient(90deg, rgba(46,230,168,.5) 50%, rgba(255,92,138,.5) 50%); }
  .k.c { height: 0; border-top: 2px dashed #a79cff; }
</style>
