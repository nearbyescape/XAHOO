<script lang="ts">
  import type { Market } from '../lib/types';
  import { px, pct } from '../lib/format';
  import { selected } from '../lib/store';
  import Roll from './Roll.svelte';
  import Needle from './Needle.svelte';
  import FlowMeter from './FlowMeter.svelte';
  import Cell from './Cell.svelte';
  export let m: Market;
  export let hs: string[];
  $: fc = m.forecast?.h || {};
  $: chg = m.price != null && m.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null;
  const blend = (keys: string[], f: typeof fc) => {
    const v = keys.map(k => f[k]).filter(x => x && x.show).map(x => x.p);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0.5;
  };
  $: slow = blend(['15m', '1h', '4h'], fc);
  $: fast = blend(['1m', '5m'], fc);
  $: hasFast = !!(fc['1m']?.show || fc['5m']?.show);
  $: liqFlash = m.liqPulse && performance.now() - m.liqPulse < 1500;
  $: stale = m.age != null && m.age > 20;
</script>
<div class="row" class:sel={$selected === m.sym} class:liq={liqFlash} class:stale role="button" tabindex="0"
     on:click={() => selected.set($selected === m.sym ? null : m.sym)} on:keydown={e => e.key === 'Enter' && selected.set(m.sym)}>
  <div class="mk">
    <div class="sym"><b>{m.short}</b>{#if m.kind === 'metal'}<span class="tag">limited history</span>{/if}</div>
    <div class="name dim">{m.name}</div>
  </div>
  <div class="pr">
    <div class="price"><Roll value={m.price} format={v => px(v, m.digits)} /></div>
    <div class="chg num" class:up={chg != null && chg >= 0} class:down={chg != null && chg < 0}>{pct(chg)}</div>
  </div>
  <div class="fl"><FlowMeter b60={m.b60} s60={m.s60} b5={m.b5} s5={m.s5} /></div>
  <div class="nd"><Needle {slow} {fast} {hasFast} /></div>
  {#each hs as h (h)}
    <Cell {h} fc={fc[h]} ribbon={m.ribbon.slice(-90).map(r => r[1][h]).filter(v => v != null)} changedAt={m.changed[h] || 0} forecastTs={m.forecast?.ts || 0} />
  {/each}
</div>
<style>
  .row { display: grid; grid-template-columns: var(--cols); align-items: stretch; border-bottom: 1px solid var(--line); cursor: pointer; transition: background .2s; min-height: 66px; }
  .row:hover { background: rgba(255,255,255,.018); }
  .row.sel { background: rgba(245,165,36,.06); box-shadow: inset 2px 0 var(--amber); }
  .row.liq { animation: liq 1.5s ease-out; }
  .row.stale { opacity: .45; }
  @keyframes liq { 0% { box-shadow: inset 0 0 0 1px var(--amber), inset 0 0 40px rgba(245,165,36,.25); } 100% { box-shadow: none; } }
  .mk, .pr, .fl, .nd { display: flex; flex-direction: column; justify-content: center; padding: 0 12px; min-width: 0; }
  .sym { display: flex; align-items: center; gap: 8px; font-size: 15px; letter-spacing: 1px; }
  .sym b { color: var(--text); }
  .tag { font-size: 8px; letter-spacing: .8px; text-transform: uppercase; color: var(--amber); border: 1px solid color-mix(in srgb, var(--amber) 45%, transparent); padding: 0 4px; }
  .name { font-size: 10px; }
  .price { font-size: 15px; font-weight: 600; }
  .chg { font-size: 10.5px; }
  .pr { align-items: flex-end; text-align: right; }
  .nd { align-items: center; }
</style>
