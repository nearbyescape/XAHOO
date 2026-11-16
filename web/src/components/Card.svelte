<script lang="ts">
  import Arrow from './Arrow.svelte';
  import type { Market } from '../lib/types';
  import { px, pct, probColor, lean, BADGE } from '../lib/format';
  import { focus, view } from '../lib/store';
  import Roll from './Roll.svelte';
  import Gauge from './Gauge.svelte';
  import Spark from './Spark.svelte';
  import HRow from './HRow.svelte';
  import LevelBar from './LevelBar.svelte';
  import FlowMeter from './FlowMeter.svelte';
  export let m: Market;
  export let hs: string[];
  $: fc = m.forecast?.h || {};
  $: chg = m.price != null && m.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null;
  const blend = (keys: string[], f: typeof fc) => {
    const v = keys.map(k => f[k]).filter(x => x && x.show).map(x => x.p);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0.5;
  };
  $: hasSlow = ['15m', '1h', '4h'].some(k => fc[k]?.show);
  $: slow = blend(['15m', '1h', '4h'], fc);
  $: fast = blend(['1m', '5m'], fc);
  $: hasFast = !!(fc['1m']?.show || fc['5m']?.show);
  $: tilt = lean(slow);
  $: label = !hasSlow ? 'No tested edge' : Math.abs(slow - 0.5) < 0.008 ? 'Neutral' : slow > 0.5 ? 'Long bias' : 'Short bias';
  $: glow = hasSlow ? Math.min(1, Math.abs(tilt)) : 0;
  $: liqFlash = m.liqPulse && performance.now() - m.liqPulse < 1500;
  $: stale = m.age != null && m.age > 20;
  $: badge = BADGE[m.sym] || ['#8b7cff', '#38c6f4'];
</script>
<div class="card panel" class:sel={$focus === m.sym} class:liq={liqFlash} class:stale
  style="--glow:{probColor(slow, 0.5 * glow)}; --edge:{probColor(slow, 0.25 + 0.5 * glow)}"
  role="button" tabindex="0" on:click={() => { focus.set(m.sym); view.set('focus'); }} on:keydown={e => { if (e.key === 'Enter') { focus.set(m.sym); view.set('focus'); } }}>
  <i class="edge"></i>
  <header>
    <span class="badge" class:long={m.short.length > 3} style="background:linear-gradient(135deg, {badge[0]}, {badge[1]})">{m.short}</span>
    <div class="id">
      <div class="sym">{m.short}<span class="pair">/USDT</span>{#if m.kind === 'metal'}<span class="chip metal">metal · new</span>{/if}</div>
      <div class="name">{m.name}</div>
    </div>
    <div class="px">
      <div class="price"><Roll value={m.price} format={v => px(v, m.digits)} /></div>
      <span class="pill num" class:upb={chg != null && chg >= 0} class:dnb={chg != null && chg < 0}>{pct(chg)} <em>24h</em></span>
    </div>
  </header>
  <div class="hero">
    <div class="dial">
      <Gauge {slow} {fast} {hasFast} size={112} />
      <div class="bias" style="color:{hasSlow ? probColor(slow) : 'var(--faint)'}">
        {#if hasSlow}<span class="num ba"><Arrow p={slow} size={18} />{((slow >= 0.5 ? slow : 1 - slow) * 100).toFixed(1)}%</span>{/if}
        <span class="bl">{label}</span>
      </div>
    </div>
    <div class="chart"><Spark data={m.spark} price={m.price} levels={m.forecast?.levels} p={hasSlow ? slow : null} /></div>
  </div>
  <div class="ladder">
    {#each hs as h (h)}
      <HRow {h} fc={fc[h]} trail={m.ribbon.slice(-90).map(r => r[1][h]).filter(v => v != null)} changedAt={m.changed[h] || 0} forecastTs={m.forecast?.ts || 0} />
    {/each}
  </div>
  {#if fc['1h']?.show && fc['1h'].reasons?.length}
    <div class="why">
      <span class="wl">Why 1h</span>
      {#each fc['1h'].reasons.slice(0, 2) as r (r.t)}
        <span class="rz" class:up={r.push > 0} class:down={r.push < 0}>{r.push > 0 ? '↑' : '↓'} <em>{r.t}</em></span>
      {/each}
    </div>
  {/if}
  <div class="sep"></div>
  <LevelBar levels={m.forecast?.levels} price={m.price} digits={m.digits} />
  <FlowMeter b60={m.b60} s60={m.s60} b5={m.b5} s5={m.s5} />
</div>
<style>
  .card { position: relative; overflow: hidden; cursor: pointer; transition: transform .25s ease, box-shadow .4s ease, border-color .4s;
    box-shadow: 0 1px 0 rgba(255,255,255,.04) inset, 0 12px 32px rgba(0,0,0,.28), 0 0 28px -8px var(--glow); border-color: color-mix(in srgb, var(--edge) 40%, var(--line)); }
  .card:hover { transform: translateY(-2px); border-color: var(--line3); }
  .card.sel { border-color: var(--accent); }
  .card.stale { opacity: .5; filter: saturate(.4); }
  .card.liq { animation: liq 1.5s ease-out; }
  @keyframes liq { 0% { box-shadow: 0 0 0 1px var(--res), 0 0 40px rgba(255,181,71,.35); } 100% { box-shadow: 0 0 0 0 transparent; } }
  .edge { position: absolute; left: 0; right: 0; top: 0; height: 2px; background: linear-gradient(90deg, transparent, var(--edge), transparent); opacity: .9; }
  header { display: flex; align-items: center; gap: 10px; padding: 13px 14px 6px; }
  .badge { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; font: 800 11px var(--sans); color: #0b0e1a; letter-spacing: .2px; flex: none;
    box-shadow: 0 4px 14px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.35); }
  .badge.long { font-size: 9px; }
  .id { min-width: 0; flex: 1; overflow: hidden; }
  .sym { font: 700 15px var(--sans); letter-spacing: .3px; display: flex; align-items: center; gap: 6px; }
  .pair { font-weight: 500; font-size: 11px; color: var(--faint); margin-left: -4px; }
  .chip.metal { color: var(--gold); border-color: color-mix(in srgb, var(--gold) 40%, transparent); font-size: 8px; padding: 1px 5px; }
  .name { font-size: 11px; color: var(--muted); }
  .px { text-align: right; }
  .price { font: 600 16px var(--mono); letter-spacing: -.3px; }
  .pill { display: inline-block; margin-top: 2px; font-size: 10.5px; padding: 1px 6px; border-radius: 6px; background: rgba(148,163,214,.08); color: var(--muted); }
  .pill em { font-style: normal; font-family: var(--sans); font-size: 9px; opacity: .7; }
  .pill.upb { color: var(--up); background: rgba(var(--up-rgb), .1); } .pill.dnb { color: var(--down); background: rgba(var(--down-rgb), .1); }
  .hero { display: grid; grid-template-columns: 126px 1fr; gap: 6px; padding: 2px 14px 6px; align-items: center; height: 96px; }
  .dial { display: flex; flex-direction: column; align-items: center; }
  .bias { display: flex; flex-direction: column; align-items: center; margin-top: 3px; line-height: 1.15; transition: color .6s; }
  .bias .num { font-size: 14px; font-weight: 700; }
  .ba { display: inline-flex; align-items: center; gap: 5px; }
  .bl { font: 600 9px var(--sans); letter-spacing: 1.2px; text-transform: uppercase; opacity: .85; }
  .chart { height: 84px; min-width: 0; }
  .ladder { padding: 4px 0 2px; }
  .why { display: flex; flex-direction: column; gap: 2px; padding: 4px 14px 2px; }
  .wl { font: 600 9px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); }
  .rz { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rz em { font-style: normal; color: var(--text); }
  .sep { height: 1px; margin: 4px 14px 0; background: var(--line); }
</style>
