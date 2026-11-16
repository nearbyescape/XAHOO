<script lang="ts">
  // Where price sits between the nearest support and resistance, with the measured chance of reaching each.
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import type { Levels } from '../lib/types';
  import { px } from '../lib/format';
  export let levels: Levels | undefined;
  export let price: number | null;
  export let digits: number;
  export let h = '1h';
  $: R = levels?.resistance?.[0];
  $: S = levels?.support?.[0];
  const pos = tweened(0.5, { duration: 600, easing: cubicOut });
  $: if (R && S && price) pos.set(Math.max(0, Math.min(1, Math.log(price / S.price) / Math.log(R.price / S.price))));
  else if (R && price) pos.set(0.15); else if (S && price) pos.set(0.85);
  const dist = (lvl: number) => (price ? (lvl / price - 1) * 100 : 0);
  const reach = (r: Record<string, number> | undefined) => (r && r[h] != null ? `${Math.round(r[h] * 100)}%` : '—');
  const conf = 'confluence: how many reasons point at this price (not a reliability score)';
</script>
<div class="lv">
  <div class="row">
    <span class="lab s">Support <span class="dots" title={conf}>{#each [1, 2, 3] as i}<i class:on={S && i <= S.strength}></i>{/each}</span></span>
    <span class="lab r"><span class="dots" title={conf}>{#each [1, 2, 3] as i}<i class:on={R && i <= R.strength}></i>{/each}</span> Resistance</span>
  </div>
  <div class="track"><i class="marker" style="left:{$pos * 100}%"></i></div>
  <div class="row">
    <span>{#if S}<b class="num">{px(S.price, digits)}</b> <span class="num d">{dist(S.price).toFixed(2)}%</span>{:else}<span class="faint">none near</span>{/if}</span>
    <span>{#if R}<span class="num d">+{dist(R.price).toFixed(2)}%</span> <b class="num">{px(R.price, digits)}</b>{:else}<span class="faint">none near</span>{/if}</span>
  </div>
  <div class="row reach">
    <span title="Measured chance price trades at this support within {h}">reach in {h} <b class="num">{reach(S?.reach)}</b></span>
    <span title="Measured chance price trades at this resistance within {h}">reach in {h} <b class="num">{reach(R?.reach)}</b></span>
  </div>
</div>
<style>
  .lv { padding: 8px 14px 4px; }
  .row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; white-space: nowrap; line-height: 1.5; }
  .lab { display: inline-flex; align-items: center; gap: 6px; font: 700 9px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; }
  .lab.s { color: var(--sup); } .lab.r { color: var(--res); }
  b { font-size: 11.5px; font-weight: 600; color: var(--text); }
  .d { font-size: 10px; color: var(--muted); }
  .dots { display: inline-flex; gap: 2px; }
  .dots i { width: 4px; height: 4px; border-radius: 50%; background: var(--line2); }
  .s .dots i.on { background: var(--sup); } .r .dots i.on { background: var(--res); }
  .track { position: relative; height: 4px; margin: 5px 0 4px; border-radius: 3px;
    background: linear-gradient(90deg, var(--sup), rgba(148,163,214,.18) 35%, rgba(148,163,214,.18) 65%, var(--res)); }
  .marker { position: absolute; top: 50%; width: 11px; height: 11px; margin-left: -5.5px; transform: translateY(-50%); border-radius: 50%;
    background: var(--text); box-shadow: 0 0 0 3px rgba(232,236,246,.12), 0 0 10px rgba(232,236,246,.5); }
  .reach { font: 500 10px var(--sans); color: var(--faint); }
  .reach b { color: var(--muted); font-size: 10.5px; }
</style>
