<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { api, resolved, horizons, markets, skill } from '../lib/store';
  import type { ScoreH } from '../lib/types';
  import { ago } from '../lib/format';
  import { now } from '../lib/store';
  let sb: Record<string, ScoreH> = {};
  let timer: ReturnType<typeof setInterval>;
  async function load() { try { sb = (await api<{ horizons: Record<string, ScoreH> }>('/api/scoreboard?days=30')).horizons; } catch { /* next time */ } }
  onMount(() => { load(); timer = setInterval(load, 30000); });
  onDestroy(() => clearInterval(timer));
  const f1 = (v: number | null | undefined) => (v == null ? '—' : (v * 100).toFixed(1));
  // tested accuracy from the walk-forward research, averaged over the coins (for comparison with live)
  $: tested = Object.fromEntries($horizons.map(h => {
    const v = Object.values($skill).map(s => s[h]).filter(s => s && s.show && s.accuracy != null && (s.n || 0) > 5000);
    return [h, v.length ? v.reduce((a, s) => a + (s.accuracy || 0), 0) / v.length : null];
  }));
</script>
<div class="panel sb">
  <div class="ph">Scoreboard <span class="r">live forecasts, last 30 days</span></div>
  <table>
    <thead><tr><th>HORIZON</th><th>SCORED</th><th title="Share of forecasts whose more-likely direction came true">HIT %</th><th title="Hit rate when the forecast was 55% or more">≥55% HIT</th><th title="Accuracy in the 2024–2026 walk-forward tests">TESTED</th></tr></thead>
    <tbody>
      {#each $horizons as h}
        {@const d = sb[h]}
        <tr>
          <td>{h}</td><td class="num">{d ? d.n.toLocaleString() : '0'}</td>
          <td class="num" class:up={d && d.hit_rate != null && d.hit_rate > 0.5} class:down={d && d.hit_rate != null && d.hit_rate < 0.5}>{f1(d?.hit_rate)}</td>
          <td class="num">{f1(d?.conf_hit_rate)}{#if d && d.conf_n}<span class="dim"> ({d.conf_n})</span>{/if}</td>
          <td class="num dim">{f1(tested[h])}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  <div class="note dim">A hit rate near the tested value means the model is behaving as it did in testing. Small samples swing widely.</div>
  <div class="ph">Calibration <span class="r">said → happened</span></div>
  <div class="cal">
    {#each ['1m', '15m', '1h'] as h}
      {@const d = sb[h]}
      <div class="calrow"><span class="hh">{h}</span>
        {#each (d?.bins || []) as b}
          <span class="bin" title="{b.label}%: {b.n} forecasts">
            <i style="height:{b.actual == null ? 0 : Math.max(4, Math.min(100, (b.actual - 0.3) / 0.4 * 100))}%" class:up={b.actual != null && b.actual > 0.5} class:down={b.actual != null && b.actual <= 0.5}></i>
            <em>{b.label}</em><strong class="num">{b.actual == null ? '—' : (b.actual * 100).toFixed(0)}</strong>
          </span>
        {/each}
      </div>
    {/each}
  </div>
  <div class="ph">Resolved <span class="r">newest first</span></div>
  <div class="feed">
    {#each $resolved.slice(0, 40) as r (r.sym + r.h + r.due)}
      {@const ok = (r.p > 0.5) === (r.outcome === 1)}
      <div class="res" class:ok class:bad={!ok}>
        <span class="mark">{ok ? '✓' : '✗'}</span>
        <span class="s">{$markets[r.sym]?.short || r.sym}</span><span class="dim">{r.h}</span>
        <span class="num">{r.p >= 0.5 ? '▲' : '▼'} {((r.p >= 0.5 ? r.p : 1 - r.p) * 100).toFixed(0)}%</span>
        <span class="num" class:up={r.ret > 0} class:down={r.ret < 0}>{(r.ret * 100 >= 0 ? '+' : '') + (r.ret * 100).toFixed(3)}%</span>
        <span class="dim num t">{ago(Math.max(0, now() - r.due))}</span>
      </div>
    {:else}
      <div class="note dim">Forecasts appear here as their time windows end.</div>
    {/each}
  </div>
</div>
<style>
  .sb { display: flex; flex-direction: column; min-height: 0; height: 100%; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 5px 12px; text-align: right; border-bottom: 1px solid var(--line); }
  th { color: var(--dim); font-weight: 400; font-size: 9px; letter-spacing: 1px; }
  th:first-child, td:first-child { text-align: left; }
  .note { padding: 7px 12px; font-size: 10px; line-height: 1.5; }
  .cal { padding: 8px 12px 4px; display: flex; flex-direction: column; gap: 8px; }
  .calrow { display: flex; align-items: flex-end; gap: 4px; }
  .hh { width: 30px; color: var(--dim); font-size: 10px; padding-bottom: 14px; }
  .bin { flex: 1; height: 54px; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; position: relative; border-bottom: 1px solid var(--line2); }
  .bin i { width: 70%; background: var(--line2); transition: height .6s ease; }
  .bin i.up { background: color-mix(in srgb, var(--up) 60%, transparent); } .bin i.down { background: color-mix(in srgb, var(--down) 60%, transparent); }
  .bin em { position: absolute; bottom: -14px; font-size: 8px; font-style: normal; color: var(--dim); white-space: nowrap; }
  .bin strong { position: absolute; top: 0; font-size: 9px; font-weight: 500; }
  .calrow { margin-bottom: 12px; }
  .feed { overflow-y: auto; flex: 1; min-height: 120px; }
  .res { display: grid; grid-template-columns: 18px 44px 30px 64px 1fr 34px; gap: 6px; padding: 3px 12px; font-size: 11px; border-bottom: 1px solid var(--line); animation: slide .35s ease-out; }
  .res .t { text-align: right; } .res .mark { font-weight: 700; }
  .ok .mark { color: var(--up); } .bad .mark { color: var(--down); }
  .bad { background: rgba(255,91,110,.035); } .ok { background: rgba(43,209,126,.03); }
  @keyframes slide { from { transform: translateX(14px); opacity: 0; } to { transform: none; opacity: 1; } }
</style>
