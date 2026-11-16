<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fly, fade } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { createChart, type IChartApi, type ISeriesApi, type IPriceLine, LineStyle } from 'lightweight-charts';
  import { api, markets, selected, skill, levelsInfo } from '../lib/store';
  import type { Market, ScoreH, Level } from '../lib/types';
  import { px, pct, usd, probColor, HORIZON_MIN, ago, BADGE, lean } from '../lib/format';
  import { now } from '../lib/store';
  import Gauge from './Gauge.svelte';
  export let sym: string;
  let el: HTMLDivElement;
  let chart: IChartApi, candles: ISeriesApi<'Candlestick'>;
  let cone: ISeriesApi<'Line'>[] = [];
  let plines: IPriceLine[] = [];
  let scaleS: ISeriesApi<'Line'>;          // invisible series that keeps the nearest levels inside the price scale
  let tf = 1;
  let hsel = '1h';
  let last: { time: number; open: number; high: number; low: number; close: number } | null = null;
  let score: Record<string, ScoreH> = {};
  let timer: ReturnType<typeof setInterval>;
  $: m = $markets[sym] as Market;
  $: fc = m?.forecast?.h || {};
  $: f = fc[hsel];
  $: sk = $skill[sym] || {};
  $: lv = m?.forecast?.levels;
  $: badge = BADGE[sym] || ['#8b7cff', '#38c6f4'];
  const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  async function load() {
    const d = await api<any>(`/api/candles?sym=${sym}&tf=${tf}&limit=400`);
    const data = d.t.map((t: number, i: number) => ({ time: t, open: d.o[i], high: d.h[i], low: d.l[i], close: d.c[i] }));
    candles.setData(data);
    last = data.length ? { ...data[data.length - 1] } : null;
    candles.applyOptions({ priceFormat: { type: 'price', precision: m.digits, minMove: 1 / 10 ** m.digits } });
    drawCone();
    drawLevels();
    chart.timeScale().setVisibleLogicalRange({ from: data.length - 150, to: data.length + coneBars() + 4 });
  }
  const coneHs = () => (tf === 1 ? ['1m', '5m', '15m', '1h'] : tf === 5 ? ['5m', '15m', '1h', '4h'] : tf === 15 ? ['15m', '1h', '4h'] : ['1h', '4h', '1d']);
  const coneBars = () => HORIZON_MIN[coneHs()[coneHs().length - 1]] / tf;
  function drawCone() {
    if (!last || !m?.forecast) { cone.forEach(s => s.setData([])); return; }
    // one point per future bar; between horizons the band grows with sqrt(time), the way volatility does
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
  function drawLevels() {
    if (!candles) return;
    plines.forEach(p => candles.removePriceLine(p));
    plines = [];
    const add = (x: Level, col: string, title: string) => plines.push(candles.createPriceLine({
      price: x.price, color: col, lineWidth: x.strength >= 3 ? 2 : 1, lineStyle: x.strength >= 2 ? LineStyle.Dashed : LineStyle.Dotted,
      axisLabelVisible: true, title }));
    (lv?.resistance || []).forEach((x, i) => add(x, css('--res'), `R${i + 1}`));
    (lv?.support || []).forEach((x, i) => add(x, css('--sup'), `S${i + 1}`));
    const keep = [lv?.resistance?.[1] || lv?.resistance?.[0], lv?.support?.[1] || lv?.support?.[0]].filter(Boolean) as Level[];
    if (last && keep.length && scaleS) scaleS.setData(keep.map((x, i) => ({ time: (last!.time - (keep.length - 1 - i) * tf * 60) as any, value: x.price })));
  }
  $: if (chart && m?.forecast) { drawCone(); drawLevels(); }
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
      layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontFamily: css('--mono'), fontSize: 11 },
      grid: { vertLines: { color: 'rgba(148,163,214,.06)' }, horzLines: { color: 'rgba(148,163,214,.06)' } },
      rightPriceScale: { borderColor: 'rgba(148,163,214,.15)' }, timeScale: { borderColor: 'rgba(148,163,214,.15)', timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0, vertLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' }, horzLine: { color: 'rgba(139,124,255,.5)', labelBackgroundColor: '#3a3470' } },
    });
    candles = chart.addCandlestickSeries({ upColor: css('--up'), downColor: css('--down'), wickUpColor: css('--up'), wickDownColor: css('--down'), borderVisible: false });
    const mk = (color: string, style: LineStyle, w: 1 | 2) => chart.addLineSeries({ color, lineStyle: style, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });
    scaleS = chart.addLineSeries({ lineVisible: false, pointMarkersVisible: false, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    cone = [mk('rgba(139,124,255,.5)', LineStyle.Dotted, 1), mk('rgba(167,156,255,.95)', LineStyle.Dashed, 2), mk('rgba(167,156,255,.95)', LineStyle.Dashed, 2), mk('rgba(139,124,255,.5)', LineStyle.Dotted, 1)];
    load(); loadScore();
    timer = setInterval(() => { load(); loadScore(); }, 60000);
  });
  onDestroy(() => { clearInterval(timer); chart?.remove(); });
  $: if (chart && sym) { tf; load(); }
  const layerNames = ['trend', 'flow', 'positioning', 'leader'];
  const bar = (v: number) => Math.max(-1, Math.min(1, v / 0.25));
  const close = () => selected.set(null);
  const dpct = (x: Level) => (m.price ? (x.price / m.price - 1) * 100 : x.dist * 100);
  const reachTxt = (x: Level, h: string) => (x.reach?.[h] != null ? `${Math.round(x.reach[h] * 100)}%` : '—');
  $: hold = $levelsInfo?.hold;
</script>
<div class="backdrop" on:click={close} on:keydown={e => e.key === 'Escape' && close()} role="presentation" transition:fade={{ duration: 200 }}></div>
<aside class="drawer" transition:fly={{ x: 60, duration: 320, easing: cubicOut }} aria-label="{m.name} details">
  <header>
    <span class="badge" class:long={m.short.length > 3} style="background:linear-gradient(135deg, {badge[0]}, {badge[1]})">{m.short}</span>
    <div><div class="t">{m.name} <span class="faint">{m.sym}</span></div>
      <div class="pr"><span class="num big">{px(m.price, m.digits)}</span>
        <span class="num" class:up={(m.price ?? 0) >= (m.dayAgo ?? 0)} class:down={(m.price ?? 0) < (m.dayAgo ?? 0)}>{pct(m.price != null && m.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null)} 24h</span></div></div>
    <span class="seg">{#each [[1, '1m'], [5, '5m'], [15, '15m'], [60, '1h']] as [v, l]}<button class:on={tf === v} on:click={() => (tf = +v)}>{l}</button>{/each}</span>
    <span class="legend"><i class="l68"></i>68% range <i class="l95"></i>95% <i class="lr"></i>resistance <i class="ls"></i>support</span>
    <button class="x" on:click={close} aria-label="Close">✕</button>
  </header>
  <div class="body">
    <div class="main">
      <div class="chart" bind:this={el}></div>
      <div class="hz">
        {#each Object.keys(HORIZON_MIN) as h}
          {@const x = fc[h]}
          <button class="hb" class:on={hsel === h} class:off={!x?.show} on:click={() => (hsel = h)}
            style={x?.show ? `--c:${probColor(x.p)}; --w:${Math.abs(lean(x.p)) * 50}%; --l:${x.p >= 0.5 ? '50%' : `calc(50% - ${Math.abs(lean(x.p)) * 50}%)`}` : ''}>
            <span class="hh num">{h}</span>
            <span class="hv num">{x?.show ? `${x.p >= 0.5 ? '▲' : '▼'} ${((x.p >= 0.5 ? x.p : 1 - x.p) * 100).toFixed(1)}%` : 'no edge'}</span>
            <span class="hbar"><i></i></span>
          </button>
        {/each}
      </div>
    </div>
    <div class="side">
      {#if f}
        <div class="block head">
          <Gauge slow={f.show ? f.p : 0.5} fast={f.show ? f.p : 0.5} hasFast={false} size={110} />
          <div>
            {#if f.show}
              <div class="pbig num" style="color:{probColor(f.p)}">{f.p >= 0.5 ? '▲' : '▼'} {((f.p >= 0.5 ? f.p : 1 - f.p) * 100).toFixed(1)}%</div>
              <div class="dim">chance {m.short} is {f.p >= 0.5 ? 'higher' : 'lower'} in {hsel}{f.tier === 1 ? ' · weak skill' : ''}</div>
            {:else}
              <div class="pbig faint">No edge</div><div class="dim">no tested skill for {m.short} at {hsel}; the range still applies</div>
            {/if}
          </div>
        </div>
        <div class="block kv2">
          <span>68% range</span><b class="num">{px(f.lo68, m.digits)} – {px(f.hi68, m.digits)}</b>
          <span>95% range</span><b class="num">{px(f.lo95, m.digits)} – {px(f.hi95, m.digits)}</b>
          <span>Expected move</span><b class="num">±{(f.move_bp / 100).toFixed(2)}%{#if !f.tradable}<em> · below costs</em>{/if}</b>
        </div>
      {/if}
      <div class="block">
        <div class="bt">Support &amp; resistance <span>reach = measured chance price trades there within</span></div>
        <div class="lvt">
          <span class="lh"></span><span class="lh">price</span><span class="lh">away</span><span class="lh">1h</span><span class="lh">4h</span><span class="lh">1d</span>
          {#each (lv?.resistance || []).slice().reverse() as x, i}
            {@const k = (lv?.resistance?.length || 0) - i}
            <span class="tag r">R{k}<span class="dots">{#each [1, 2, 3] as j}<i class:on={j <= x.strength}></i>{/each}</span></span>
            <span class="num pr2" title={x.sources.join(' · ') + ` · ${x.reactions} reactions`}>{px(x.price, m.digits)}</span>
            <span class="num dim">+{dpct(x).toFixed(2)}%</span>
            <span class="num">{reachTxt(x, '1h')}</span><span class="num">{reachTxt(x, '4h')}</span><span class="num">{reachTxt(x, '1d')}</span>
          {/each}
          <span class="tag now">NOW</span><span class="num pr2 nowp">{px(m.price, m.digits)}</span><span></span><span></span><span></span><span></span>
          {#each lv?.support || [] as x, i}
            <span class="tag s">S{i + 1}<span class="dots">{#each [1, 2, 3] as j}<i class:on={j <= x.strength}></i>{/each}</span></span>
            <span class="num pr2" title={x.sources.join(' · ') + ` · ${x.reactions} reactions`}>{px(x.price, m.digits)}</span>
            <span class="num dim">{dpct(x).toFixed(2)}%</span>
            <span class="num">{reachTxt(x, '1h')}</span><span class="num">{reachTxt(x, '4h')}</span><span class="num">{reachTxt(x, '1d')}</span>
          {/each}
        </div>
        <div class="note">Levels: swing highs and lows (15m, 1h), prior-day and 7-day extremes, and volume nodes from the last 7 days; dots = confluence (how many reasons point there). Hover a price for its sources.
          {#if hold?.res?.level}<br><b class="hon">How much they hold:</b> in 2024–26 tests on the coins, an hour after price touched a resistance it was back below {(hold.res.level.held60 * 100).toFixed(1)}% of the time, against {(hold.res.control.held60 * 100).toFixed(1)}% at arbitrary prices the same distance away; supports {(hold.sup.level.held60 * 100).toFixed(1)}% against {(hold.sup.control.held60 * 100).toFixed(1)}%.
            {#if Math.abs(hold.res.diff60) < 2 * hold.res.diff60_se + 0.01 && Math.abs(hold.sup.diff60) < 2 * hold.sup.diff60_se + 0.01}No better than chance: use them as reference prices and for the reach chances, not as turning points.{/if}{/if}</div>
      </div>
      {#if f && f.show && Object.keys(f.layers).length}
        <div class="block">
          <div class="bt">Why <span>what pushes the {hsel} probability</span></div>
          <div class="why">
            {#each layerNames.filter(k => k in f.layers) as k}
              {@const v = f.layers[k]}
              <span class="ln">{k}</span>
              <span class="track"><i class:up={v > 0} class:down={v < 0} style="width:{Math.abs(bar(v)) * 50}%; {v >= 0 ? 'left:50%' : 'right:50%'}"></i></span>
              <span class="num lv" class:up={v > 0.005} class:down={v < -0.005}>{v > 0 ? '+' : ''}{v.toFixed(2)}</span>
            {/each}
          </div>
        </div>
      {/if}
      <div class="block kv2">
        <span>Open interest, 1h</span><b class="num" class:up={(m.oiChg1h ?? 0) > 0} class:down={(m.oiChg1h ?? 0) < 0}>{pct(m.oiChg1h != null ? m.oiChg1h * 100 : null)}</b>
        <span>Long / short accounts</span><b class="num">{m.lsRatio != null ? m.lsRatio.toFixed(2) : '—'}</b>
        <span>Funding rate</span><b class="num" class:up={(m.funding ?? 0) > 0} class:down={(m.funding ?? 0) < 0}>{m.funding != null ? (m.funding * 100).toFixed(4) + '%' : '—'}</b>
        <span>Flow, last 60 s</span><b class="num" class:up={m.b60 > m.s60} class:down={m.b60 < m.s60}>{usd(m.b60 - m.s60)}</b>
      </div>
      {#if m.liqs.length}
        <div class="block">
          <div class="bt">Liquidations</div>
          <div class="liqs">{#each m.liqs.slice(-6).reverse() as l}<div><span class:down={l.side === 'long'} class:up={l.side === 'short'}>{l.side}s closed</span><span class="num">{usd(l.usd).slice(1)}</span><span class="num dim">@ {px(l.price, m.digits)}</span><span class="dim num">{ago(Math.max(0, now() - l.ts / 1000))}</span></div>{/each}</div>
        </div>
      {/if}
      <div class="block">
        <div class="bt">Track record <span>{m.short}, live, 30 days</span></div>
        <table>
          <thead><tr><th></th><th>scored</th><th>hit %</th><th>tested</th></tr></thead>
          <tbody>{#each Object.keys(HORIZON_MIN) as h}
            {@const d = score[h]}{@const s = sk[h]}
            <tr class:off={!s?.show}><td class="num">{h}</td><td class="num">{d ? d.n : 0}</td><td class="num">{d?.hit_rate != null ? (d.hit_rate * 100).toFixed(1) : '—'}</td>
              <td class="num dim">{s?.show && s.accuracy != null ? (s.accuracy * 100).toFixed(1) : 'no edge'}</td></tr>
          {/each}</tbody>
        </table>
        {#if m.kind === 'metal'}<div class="note">Binance lists {m.name.toLowerCase()} since {m.sym === 'XAUUSDT' ? 'December 2025' : 'January 2026'}; skill figures rest on limited history. It trades through weekends, when the underlying market is closed.</div>{/if}
      </div>
    </div>
  </div>
</aside>
<style>
  .backdrop { position: fixed; inset: 0; background: rgba(4, 6, 14, .55); backdrop-filter: blur(3px); z-index: 40; }
  .drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(1280px, 100vw); z-index: 41; display: flex; flex-direction: column;
    background: linear-gradient(180deg, #0f1426, #0a0e1b); border-left: 1px solid var(--line2); box-shadow: -30px 0 80px rgba(0,0,0,.5); }
  header { display: flex; align-items: center; gap: 14px; padding: 14px 20px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
  .badge { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font: 800 12px var(--sans); color: #0b0e1a; box-shadow: inset 0 1px 0 rgba(255,255,255,.35); }
  .badge.long { font-size: 10px; }
  .t { font: 700 15px var(--sans); } .t .faint { font-weight: 500; font-size: 11px; margin-left: 4px; }
  .pr { display: flex; align-items: baseline; gap: 10px; } .big { font-size: 18px; font-weight: 600; }
  .seg { display: inline-flex; gap: 4px; margin-left: 10px; } .seg button { padding: 3px 10px; font-size: 11px; }
  .legend { display: inline-flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--muted); margin-left: auto; }
  .legend i { display: inline-block; width: 16px; height: 0; border-top: 2px dashed #a79cff; margin-left: 6px; }
  .legend i.l95 { border-top: 1px dotted #8b7cff; } .legend i.lr { border-top-color: var(--res); } .legend i.ls { border-top-color: var(--sup); }
  .x { font-size: 14px; padding: 4px 10px; }
  .body { display: grid; grid-template-columns: minmax(0, 1fr) 400px; flex: 1; min-height: 0; }
  .main { display: flex; flex-direction: column; min-width: 0; padding: 10px 12px 14px 20px; gap: 12px; }
  .chart { flex: 1; min-height: 320px; }
  .hz { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
  .hb { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 8px 10px; border-radius: 10px; background: rgba(148,163,214,.04); text-align: left; }
  .hb.on { background: rgba(139,124,255,.12); border-color: var(--accent); color: var(--text); font-weight: 500; }
  .hh { font-size: 11px; color: var(--muted); } .hv { font-size: 14px; font-weight: 700; color: var(--c, var(--faint)); }
  .hb.off .hv { font: 500 11px var(--sans); }
  .hbar { position: relative; width: 100%; height: 4px; border-radius: 2px; background: rgba(148,163,214,.1); }
  .hbar i { position: absolute; top: 0; bottom: 0; left: var(--l, 50%); width: var(--w, 0); background: var(--c); border-radius: 2px; transition: all .6s; }
  .side { border-left: 1px solid var(--line); overflow-y: auto; }
  .block { padding: 14px 18px; border-bottom: 1px solid var(--line); }
  .head { display: flex; align-items: center; gap: 14px; }
  .pbig { font-size: 28px; font-weight: 700; letter-spacing: -.5px; line-height: 1.1; }
  .bt { font: 600 10.5px var(--sans); letter-spacing: 1.3px; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }
  .bt span { text-transform: none; letter-spacing: 0; color: var(--faint); font-weight: 500; margin-left: 6px; }
  .kv2 { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; }
  .kv2 span { color: var(--muted); } .kv2 b { text-align: right; font-weight: 500; } .kv2 em { font-style: normal; font-size: 10px; color: var(--faint); }
  .lvt { display: grid; grid-template-columns: 56px 1fr 62px 40px 40px 40px; gap: 5px 8px; align-items: center; font-size: 12px; }
  .lvt > span:nth-child(6n+4), .lvt > span:nth-child(6n+5), .lvt > span:nth-child(6n+6), .lvt > span:nth-child(6n+3) { text-align: right; }
  .lh { font: 600 9px var(--sans); letter-spacing: 1px; text-transform: uppercase; color: var(--faint); }
  .tag { display: inline-flex; align-items: center; gap: 5px; font: 700 10px var(--sans); }
  .tag.r { color: var(--res); } .tag.s { color: var(--sup); } .tag.now { color: var(--text); }
  .dots { display: inline-flex; gap: 2px; } .dots i { width: 4px; height: 4px; border-radius: 50%; background: var(--line2); }
  .tag.r .dots i.on { background: var(--res); } .tag.s .dots i.on { background: var(--sup); }
  .pr2 { font-weight: 600; cursor: help; } .nowp { color: var(--text); }
  .note { font-size: 10.5px; color: var(--faint); line-height: 1.55; margin-top: 10px; }
  .hon { color: var(--muted); font-weight: 600; }
  .why { display: grid; grid-template-columns: 84px 1fr 44px; gap: 8px; align-items: center; }
  .ln { color: var(--muted); text-transform: capitalize; } .lv { text-align: right; }
  .track { position: relative; height: 7px; border-radius: 4px; background: rgba(148,163,214,.08); }
  .track::after { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line3); }
  .track i { position: absolute; top: 0; bottom: 0; border-radius: 4px; transition: width .6s ease; }
  .track i.up { background: var(--up); } .track i.down { background: var(--down); }
  .liqs div { display: grid; grid-template-columns: 96px 60px 1fr 36px; gap: 6px; padding: 2px 0; font-size: 11.5px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 4px 0; text-align: right; border-bottom: 1px solid var(--line); font-size: 12px; }
  th { color: var(--faint); font: 600 9px var(--sans); letter-spacing: 1px; text-transform: uppercase; } th:first-child, td:first-child { text-align: left; }
  tr.off td { color: var(--faint); }
  @media (max-width: 1000px) {
    .body { grid-template-columns: 1fr; overflow-y: auto; } .side { border-left: 0; border-top: 1px solid var(--line); overflow: visible; }
    .chart { min-height: 300px; height: 300px; flex: none; } .hz { grid-template-columns: repeat(3, 1fr); } .legend { display: none; }
  }
</style>
