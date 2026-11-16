<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createChart, type IChartApi, type ISeriesApi, LineStyle } from 'lightweight-charts';
  import { api, markets, selected, skill } from '../lib/store';
  import type { Market, ScoreH } from '../lib/types';
  import { px, pct, usd, probColor, HORIZON_MIN, ago } from '../lib/format';
  import { now } from '../lib/store';
  export let sym: string;
  let el: HTMLDivElement;
  let chart: IChartApi, candles: ISeriesApi<'Candlestick'>;
  let cone: ISeriesApi<'Line'>[] = [];
  let tf = 1;
  let hsel = '1h';
  let last: { time: number; open: number; high: number; low: number; close: number } | null = null;
  let score: Record<string, ScoreH> = {};
  let timer: ReturnType<typeof setInterval>;
  $: m = $markets[sym] as Market;
  $: fc = m?.forecast?.h || {};
  $: f = fc[hsel];
  $: sk = $skill[sym] || {};
  const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  async function load() {
    const d = await api<any>(`/api/candles?sym=${sym}&tf=${tf}&limit=400`);
    const data = d.t.map((t: number, i: number) => ({ time: t, open: d.o[i], high: d.h[i], low: d.l[i], close: d.c[i] }));
    candles.setData(data);
    last = data.length ? { ...data[data.length - 1] } : null;
    candles.applyOptions({ priceFormat: { type: 'price', precision: m.digits, minMove: 1 / 10 ** m.digits } });
    drawCone();
    chart.timeScale().setVisibleLogicalRange({ from: data.length - 150, to: data.length + coneBars() + 4 });
  }
  // how many bars into the future the cone reaches on this timeframe
  const coneHs = () => (tf === 1 ? ['1m', '5m', '15m', '1h'] : tf === 5 ? ['5m', '15m', '1h', '4h'] : tf === 15 ? ['15m', '1h', '4h'] : ['1h', '4h', '1d']);
  const coneBars = () => HORIZON_MIN[coneHs()[coneHs().length - 1]] / tf;
  function drawCone() {
    if (!last || !m?.forecast) { cone.forEach(s => s.setData([])); return; }
    // The chart spaces points evenly per bar, so the cone needs one point for every future bar. Between the
    // forecast horizons the band is interpolated in sqrt(time), the way volatility grows.
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
  $: if (chart && m?.forecast) drawCone();
  // live candle
  $: if (candles && last && m?.price != null) {
    const bucket = Math.floor(now() / (tf * 60)) * tf * 60;
    if (bucket > last.time) last = { time: bucket, open: last.close, high: Math.max(last.close, m.price), low: Math.min(last.close, m.price), close: m.price };
    else { last.high = Math.max(last.high, m.price); last.low = Math.min(last.low, m.price); last.close = m.price; }
    candles.update({ ...last, time: last.time as any });
  }
  async function loadScore() { try { score = (await api<any>(`/api/scoreboard?sym=${sym}&days=30`)).horizons; } catch { /* later */ } }

  onMount(() => {
    chart = createChart(el, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: css('--dim'), fontFamily: css('--font'), fontSize: 11 },
      grid: { vertLines: { color: css('--line') }, horzLines: { color: css('--line') } },
      rightPriceScale: { borderColor: css('--line2') }, timeScale: { borderColor: css('--line2'), timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });
    candles = chart.addCandlestickSeries({ upColor: css('--up'), downColor: css('--down'), wickUpColor: css('--up'), wickDownColor: css('--down'), borderVisible: false });
    const mk = (color: string, style: LineStyle, w: 1 | 2) => chart.addLineSeries({ color, lineStyle: style, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    cone = [mk('rgba(245,165,36,.45)', LineStyle.Dotted, 1), mk('rgba(245,165,36,.95)', LineStyle.Dashed, 2), mk('rgba(245,165,36,.95)', LineStyle.Dashed, 2), mk('rgba(245,165,36,.45)', LineStyle.Dotted, 1)];
    load(); loadScore();
    timer = setInterval(() => { load(); loadScore(); }, 60000);
  });
  onDestroy(() => { clearInterval(timer); chart?.remove(); });
  $: if (chart && sym) { tf; load(); }
  const layerNames = ['trend', 'flow', 'positioning', 'leader'];
  const bar = (v: number) => Math.max(-1, Math.min(1, v / 0.25));
</script>
<section class="detail panel">
  <div class="ph">
    <span class="t">{m.short} · {m.name}</span>
    <span class="num big">{px(m.price, m.digits)}</span>
    <span class="num" class:up={(m.price ?? 0) >= (m.dayAgo ?? 0)} class:down={(m.price ?? 0) < (m.dayAgo ?? 0)}>{pct(m.price != null && m.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null)}</span>
    <span class="seg">{#each [[1, '1m'], [5, '5m'], [15, '15m'], [60, '1h']] as [v, l]}<button class:on={tf === v} on:click={() => (tf = +v)}>{l}</button>{/each}</span>
    <span class="r"><span class="legend"><i class="l68"></i>68% range <i class="l95"></i>95% range</span><button on:click={() => selected.set(null)}>✕</button></span>
  </div>
  <div class="grid">
    <div class="chart" bind:this={el}></div>
    <div class="side">
      <div class="ph2">Horizon <span class="seg">{#each Object.keys(HORIZON_MIN) as h}<button class:on={hsel === h} on:click={() => (hsel = h)}>{h}</button>{/each}</span></div>
      {#if f}
        <div class="headline">
          {#if f.show}
            <span class="pbig num" style="color:{probColor(f.p)}">{f.p >= 0.5 ? '▲' : '▼'} {((f.p >= 0.5 ? f.p : 1 - f.p) * 100).toFixed(1)}%</span>
            <span class="dim">chance {m.short} is {f.p >= 0.5 ? 'higher' : 'lower'} in {hsel}{f.tier === 1 ? ' · weak skill' : ''}</span>
          {:else}
            <span class="pbig dim">no edge</span><span class="dim">no tested skill for {m.short} at {hsel}; range still applies</span>
          {/if}
        </div>
        <div class="kv2">
          <span>68% range</span><b class="num">{px(f.lo68, m.digits)} – {px(f.hi68, m.digits)}</b>
          <span>95% range</span><b class="num">{px(f.lo95, m.digits)} – {px(f.hi95, m.digits)}</b>
          <span>Expected move</span><b class="num">±{(f.move_bp / 100).toFixed(2)}%{#if !f.tradable}<em class="dim"> · below typical costs</em>{/if}</b>
        </div>
        {#if f.show && Object.keys(f.layers).length}
          <div class="ph2">Why <span class="dim">what pushes the probability</span></div>
          <div class="why">
            {#each layerNames.filter(k => k in f.layers) as k}
              {@const v = f.layers[k]}
              <span class="ln">{k}</span>
              <span class="track"><i class:up={v > 0} class:down={v < 0} style="width:{Math.abs(bar(v)) * 50}%; {v >= 0 ? 'left:50%' : `right:50%`}"></i></span>
              <span class="num lv" class:up={v > 0.005} class:down={v < -0.005}>{v > 0 ? '+' : ''}{v.toFixed(2)}</span>
            {/each}
          </div>
        {/if}
      {/if}
      <div class="ph2">Positioning</div>
      <div class="kv2">
        <span>Open interest, 1h</span><b class="num" class:up={(m.oiChg1h ?? 0) > 0} class:down={(m.oiChg1h ?? 0) < 0}>{pct(m.oiChg1h != null ? m.oiChg1h * 100 : null)}</b>
        <span>Long / short accounts</span><b class="num">{m.lsRatio != null ? m.lsRatio.toFixed(2) : '—'}</b>
        <span>Funding rate</span><b class="num" class:up={(m.funding ?? 0) > 0} class:down={(m.funding ?? 0) < 0}>{m.funding != null ? (m.funding * 100).toFixed(4) + '%' : '—'}</b>
        <span>Flow, last 60 s</span><b class="num" class:up={m.b60 > m.s60} class:down={m.b60 < m.s60}>{usd(m.b60 - m.s60)}</b>
      </div>
      {#if m.liqs.length}
        <div class="ph2">Liquidations</div>
        <div class="liqs">{#each m.liqs.slice(-6).reverse() as l}<div><span class:down={l.side === 'long'} class:up={l.side === 'short'}>{l.side} closed</span><span class="num">{usd(l.usd)}</span><span class="num dim">@ {px(l.price, m.digits)}</span><span class="dim num">{ago(Math.max(0, now() - l.ts / 1000))}</span></div>{/each}</div>
      {/if}
      <div class="ph2">Track record <span class="dim">{m.short}, live, 30 days</span></div>
      <table>
        <thead><tr><th></th><th>SCORED</th><th>HIT %</th><th>TESTED</th></tr></thead>
        <tbody>{#each Object.keys(HORIZON_MIN) as h}
          {@const d = score[h]}{@const s = sk[h]}
          <tr class:off={!s?.show}><td>{h}</td><td class="num">{d ? d.n : 0}</td><td class="num">{d?.hit_rate != null ? (d.hit_rate * 100).toFixed(1) : '—'}</td>
            <td class="num dim">{s?.show && s.accuracy != null ? (s.accuracy * 100).toFixed(1) : 'no edge'}</td></tr>
        {/each}</tbody>
      </table>
      {#if m.kind === 'metal'}<div class="note dim">Binance lists {m.name.toLowerCase()} since {m.sym === 'XAUUSDT' ? 'December 2025' : 'January 2026'}; skill figures rest on limited history. It trades through weekends, when the underlying market is closed.</div>{/if}
    </div>
  </div>
</section>
<style>
  .detail { display: flex; flex-direction: column; }
  .ph .t { color: var(--text); font-size: 12px; letter-spacing: 1px; }
  .big { font-size: 14px; color: var(--text); letter-spacing: 0; }
  .seg { display: inline-flex; }
  .seg button { border-right-width: 0; padding: 1px 8px; font-size: 10px; letter-spacing: 0; text-transform: none; color: var(--dim); }
  .seg button:last-child { border-right-width: 1px; } .seg button.on { color: var(--bg); }
  .legend { display: inline-flex; align-items: center; gap: 6px; margin-right: 12px; font-size: 10px; }
  .legend i { display: inline-block; width: 16px; height: 0; border-top: 2px dashed var(--amber); }
  .legend i.l95 { border-top: 1px dotted var(--amber); opacity: .7; }
  .grid { display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: 0; }
  .chart { height: 420px; min-width: 0; }
  .side { border-left: 1px solid var(--line); overflow-y: auto; max-height: 420px; }
  .ph2 { display: flex; align-items: center; gap: 8px; padding: 6px 12px; font-size: 9.5px; letter-spacing: 1.4px; text-transform: uppercase; color: var(--amber); border-bottom: 1px solid var(--line); border-top: 1px solid var(--line); }
  .ph2:first-child { border-top: 0; } .ph2 .dim { text-transform: none; letter-spacing: 0; } .ph2 .seg { margin-left: auto; }
  .headline { padding: 10px 12px 4px; display: flex; flex-direction: column; gap: 2px; }
  .pbig { font-size: 26px; font-weight: 700; letter-spacing: -.5px; }
  .kv2 { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; padding: 8px 12px; }
  .kv2 span { color: var(--dim); } .kv2 b { text-align: right; font-weight: 500; } .kv2 em { font-style: normal; font-size: 10px; }
  .why { display: grid; grid-template-columns: 84px 1fr 44px; gap: 6px 8px; align-items: center; padding: 8px 12px; }
  .ln { color: var(--dim); } .lv { text-align: right; }
  .track { position: relative; height: 8px; background: var(--panel2); border-left: 1px solid transparent; }
  .track::after { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line2); }
  .track i { position: absolute; top: 0; bottom: 0; transition: width .6s ease; }
  .track i.up { background: var(--up); } .track i.down { background: var(--down); }
  .liqs div { display: grid; grid-template-columns: 92px 70px 1fr 40px; gap: 6px; padding: 3px 12px; font-size: 11px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 4px 12px; text-align: right; border-bottom: 1px solid var(--line); }
  th { color: var(--dim); font-weight: 400; font-size: 9px; letter-spacing: 1px; } th:first-child, td:first-child { text-align: left; }
  tr.off td { color: var(--dimmer); }
  .note { padding: 8px 12px; font-size: 10px; line-height: 1.5; }
  @media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } .side { border-left: 0; border-top: 1px solid var(--line); max-height: none; } .chart { height: 320px; } }
</style>
