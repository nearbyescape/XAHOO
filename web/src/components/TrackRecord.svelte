<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { flip } from 'svelte/animate';
  import { fly } from 'svelte/transition';
  import { api, resolved, horizons, markets, skill } from '../lib/store';
  import type { ScoreH } from '../lib/types';
  import { ago } from '../lib/format';
  import CoinLogo from './CoinLogo.svelte';
  import { now } from '../lib/store';
  let sb: Record<string, ScoreH> = {};
  let timer: ReturnType<typeof setInterval>;
  async function load() { try { sb = (await api<{ horizons: Record<string, ScoreH> }>('/api/scoreboard?days=30')).horizons; } catch { /* next time */ } }
  onMount(() => { load(); timer = setInterval(load, 30000); });
  onDestroy(() => clearInterval(timer));
  const f1 = (v: number | null | undefined) => (v == null ? '—' : (v * 100).toFixed(1));
  // accuracy in the 2024–2026 walk-forward tests, averaged over markets with enough samples
  $: tested = Object.fromEntries($horizons.map(h => {
    const v = Object.values($skill).map(s => s[h]).filter(s => s && s.show && s.accuracy != null && (s.n || 0) > 5000);
    return [h, v.length ? v.reduce((a, s) => a + (s.accuracy || 0), 0) / v.length : null];
  }));
  const calH = ['1m', '5m', '15m', '1h'];
  let calSel = '1m';
  $: bins = sb[calSel]?.bins || [];
</script>
<section class="tr panel">
  <div class="col">
    <div class="ph">Live track record <span class="r">last 30 days · forecasts the screen showed</span></div>
    <div class="tiles">
      {#each $horizons as h}
        {@const d = sb[h]}{@const t = tested[h]}
        <div class="tile">
          <div class="th"><span class="hz num">{h}</span><span class="n num">{d ? d.n.toLocaleString() : 0} scored</span></div>
          <div class="hit num" class:up={d?.hit_rate != null && d.hit_rate > 0.5} class:down={d?.hit_rate != null && d.hit_rate < 0.5}>{f1(d?.hit_rate)}<small>%</small></div>
          <div class="cmp"><i class="live" style="width:{d?.hit_rate != null ? Math.max(0, Math.min(1, (d.hit_rate - 0.4) / 0.25)) * 100 : 0}%"></i>
            {#if t != null}<i class="tick" style="left:{Math.max(0, Math.min(1, (t - 0.4) / 0.25)) * 100}%" title="tested {f1(t)}%"></i>{/if}</div>
          <div class="ft"><span>tested <b class="num">{f1(t)}</b></span><span title="Hit rate when the forecast was 55% or more">≥55% <b class="num">{f1(d?.conf_hit_rate)}</b></span></div>
        </div>
      {/each}
    </div>
    <div class="note">Hit = the more likely direction came true. Near the tested value means the model behaves as it did in testing; small samples swing widely.</div>
  </div>
  <div class="col">
    <div class="ph">Calibration <span class="r">said → happened</span>
      <span class="seg">{#each calH as h}<button class:on={calSel === h} on:click={() => (calSel = h)}>{h}</button>{/each}</span></div>
    <div class="cal">
      {#each bins as b}
        <div class="bin" title="{b.label}%: {b.n} forecasts">
          <span class="v num">{b.actual == null ? '—' : (b.actual * 100).toFixed(0)}</span>
          <div class="well">
            {#if b.predicted != null}<i class="pred" style="bottom:{Math.max(0, Math.min(1, (b.predicted - 0.3) / 0.4)) * 100}%"></i>{/if}
            <i class="act" class:up={b.actual != null && b.actual > 0.5} class:down={b.actual != null && b.actual <= 0.5}
               style="height:{b.actual == null ? 0 : Math.max(3, Math.min(100, ((b.actual - 0.3) / 0.4) * 100))}%"></i>
          </div>
          <span class="lb">{b.label}</span><span class="cnt num">{b.n}</span>
        </div>
      {:else}<div class="note">Builds up as forecasts resolve.</div>{/each}
    </div>
    <div class="note">Bars: how often price actually went up for forecasts in each band. White tick: what was forecast.</div>
  </div>
  <div class="col feedcol">
    <div class="ph">Resolved <span class="r">newest first</span></div>
    <div class="feed">
      {#each $resolved.slice(0, 30) as r (r.sym + r.h + r.due)}
        {@const ok = (r.p > 0.5) === (r.outcome === 1)}
        <div class="res" class:ok animate:flip={{ duration: 300 }} in:fly={{ x: 16, duration: 350 }}>
          <span class="mk">{ok ? '✓' : '✗'}</span>
          <span class="s"><CoinLogo sym={r.sym} short={$markets[r.sym]?.short || ''} size={16} glow={false} />{$markets[r.sym]?.short || r.sym}</span><span class="hz num">{r.h}</span>
          <span class="num p">{r.p >= 0.5 ? '▲' : '▼'} {((r.p >= 0.5 ? r.p : 1 - r.p) * 100).toFixed(0)}%</span>
          <span class="num" class:up={r.ret > 0} class:down={r.ret < 0}>{(r.ret >= 0 ? '+' : '−') + Math.abs(r.ret * 100).toFixed(3)}%</span>
          <span class="num t">{ago(Math.max(0, now() - r.due))}</span>
        </div>
      {:else}
        <div class="note">Forecasts appear here as their windows end.</div>
      {/each}
    </div>
  </div>
</section>
<style>
  .tr { display: grid; grid-template-columns: 1.35fr 1fr 1fr; min-height: 0; }
  .col { display: flex; flex-direction: column; min-width: 0; border-left: 1px solid var(--line); }
  .col:first-child { border-left: 0; }
  .ph .seg { margin-left: 8px; display: inline-flex; gap: 3px; }
  .ph .seg button { padding: 1px 7px; font-size: 10px; letter-spacing: 0; text-transform: none; border-radius: 6px; }
  .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 0 16px; }
  .tile { background: rgba(148,163,214,.04); border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; }
  .th { display: flex; justify-content: space-between; align-items: baseline; }
  .hz { font-weight: 700; font-size: 12px; color: var(--text); }
  .n { font-size: 10px; color: var(--faint); }
  .hit { font-size: 22px; font-weight: 700; line-height: 1.2; } .hit small { font-size: 12px; opacity: .7; }
  .cmp { position: relative; height: 4px; border-radius: 2px; background: rgba(148,163,214,.1); margin: 3px 0 5px; }
  .cmp .live { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; background: var(--brand); transition: width .6s; }
  .cmp .tick { position: absolute; top: -3px; bottom: -3px; width: 2px; margin-left: -1px; background: var(--text); border-radius: 1px; }
  .ft { display: flex; justify-content: space-between; font-size: 10px; color: var(--faint); }
  .ft b { color: var(--muted); font-weight: 500; }
  .note { padding: 8px 16px 12px; font-size: 10.5px; color: var(--faint); line-height: 1.5; }
  .cal { display: flex; gap: 6px; padding: 4px 16px 0; height: 150px; align-items: stretch; }
  .bin { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 0; }
  .bin .v { font-size: 11px; font-weight: 600; }
  .well { position: relative; flex: 1; width: 100%; border-radius: 6px; background: rgba(148,163,214,.05); overflow: hidden; }
  .act { position: absolute; left: 18%; right: 18%; bottom: 0; border-radius: 4px 4px 0 0; background: var(--line2); transition: height .6s ease; }
  .act.up { background: linear-gradient(180deg, var(--up), rgba(var(--up-rgb), .25)); } .act.down { background: linear-gradient(180deg, var(--down), rgba(var(--down-rgb), .25)); }
  .pred { position: absolute; left: 8%; right: 8%; height: 2px; background: var(--text); z-index: 1; border-radius: 1px; }
  .lb { font-size: 9px; color: var(--muted); white-space: nowrap; } .cnt { font-size: 9px; color: var(--faint); }
  .feed { overflow-y: auto; flex: 1; min-height: 0; max-height: 236px; padding: 0 8px 8px; }
  .res { display: grid; grid-template-columns: 16px 58px 30px 56px 1fr 30px; gap: 6px; align-items: center; padding: 4px 8px; font-size: 11px; border-radius: 6px; }
  .res:nth-child(odd) { background: rgba(148,163,214,.03); }
  .res .mk { font-weight: 800; color: var(--down); } .res.ok .mk { color: var(--up); }
  .res .s { display: flex; align-items: center; gap: 5px; font-weight: 600; font-size: 11px; }
  .res .hz { color: var(--muted); font-size: 10.5px; font-weight: 500; }
  .res .p { color: var(--muted); } .res .t { text-align: right; color: var(--faint); font-size: 10px; }
  @media (max-width: 1200px) { .tr { grid-template-columns: 1fr; } .col { border-left: 0; border-top: 1px solid var(--line); } .col:first-child { border-top: 0; } }
  @media (max-width: 560px) { .tiles { grid-template-columns: repeat(2, 1fr); } }
</style>
