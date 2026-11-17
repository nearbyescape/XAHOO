<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fly } from 'svelte/transition';
  import { api, resolved, horizons, markets, skill, now } from '../lib/store';
  import type { ScoreH } from '../lib/types';
  import { ago } from '../lib/format';
  // Live track record of the chosen market only: hit rate per timeframe over 30 days (with the tested figure
  // underneath for comparison) and its latest resolved forecasts.
  export let sym: string;
  let sb: Record<string, ScoreH> = {};
  let timer: ReturnType<typeof setInterval>;
  let loaded = '';
  async function load(s: string) {
    try { const r = await api<{ horizons: Record<string, ScoreH> }>(`/api/scoreboard?days=30&sym=${encodeURIComponent(s)}`); if (s === sym) sb = r.horizons; } catch { /* later */ }
  }
  $: if (sym !== loaded) { loaded = sym; sb = {}; load(sym); }
  onMount(() => { timer = setInterval(() => load(sym), 30000); });
  onDestroy(() => clearInterval(timer));
  $: tested = Object.fromEntries($horizons.map(h => {
    const s = $skill[sym]?.[h];
    return [h, s && s.show && s.accuracy != null ? s.accuracy : null];
  }));
  $: feed = $resolved.filter(r => r.sym === sym).slice(0, 14);
</script>
<section class="tm panel">
  <div class="ph">Track record · {$markets[sym]?.short || sym} <span class="r">live 30 days · <em>tested</em></span></div>
  <div class="tiles">
    {#each $horizons as h}
      {@const d = sb[h]}
      <div class="t"><span class="h num">{h}</span>
        <b class="num" class:up={d?.hit_rate != null && d.hit_rate > 0.5} class:down={d?.hit_rate != null && d.hit_rate < 0.5}>{d?.hit_rate != null ? (d.hit_rate * 100).toFixed(1) : '—'}%</b>
        <span class="s num">{d?.n || 0} calls · tested {tested[h] != null ? (tested[h] * 100).toFixed(1) + '%' : '—'}</span></div>
    {/each}
  </div>
  <div class="feed">
    {#each feed as r (r.sym + r.h + r.due)}
      {@const ok = (r.p > 0.5) === (r.outcome === 1)}
      <div class="res" class:ok in:fly={{ x: 14, duration: 300 }}>
        <span class="mk">{ok ? '✓' : '✗'}</span><b class="num">{r.h}</b><span class="dim">{ok ? 'right' : 'wrong'}</span>
        <span class="num">{r.p >= 0.5 ? '▲' : '▼'}{((r.p >= 0.5 ? r.p : 1 - r.p) * 100).toFixed(0)}%</span>
        <span class="num" class:up={r.ret > 0} class:down={r.ret < 0}>{(r.ret >= 0 ? '+' : '−') + Math.abs(r.ret * 100).toFixed(3)}%</span>
        <span class="num faint">{ago(Math.max(0, now() - r.due))}</span>
      </div>
    {:else}<div class="faint e">Forecasts appear here as their windows end.</div>{/each}
  </div>
</section>
<style>
  .tm { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding: 0 14px; }
  .t { display: grid; grid-template-columns: auto 1fr; align-items: baseline; gap: 0 8px; padding: 5px 9px; border-radius: 8px; background: rgba(148,163,214,.04); border: 1px solid var(--line); }
  .h { font-size: 11px; color: var(--muted); font-weight: 600; } .t b { font-size: 15px; text-align: right; }
  .s { grid-column: 1 / 3; font-size: 9.5px; color: var(--faint); }
  .feed { flex: 1; overflow-y: auto; padding: 8px 10px; min-height: 0; }
  .res { display: grid; grid-template-columns: 14px 34px 40px 44px 1fr 28px; align-items: center; gap: 6px; font-size: 11px; padding: 2px 4px; border-radius: 5px; }
  .res:nth-child(odd) { background: rgba(148,163,214,.03); }
  .mk { font-weight: 800; color: var(--down); } .res.ok .mk { color: var(--up); }
  .e { font-size: 11px; padding: 6px; }
</style>
