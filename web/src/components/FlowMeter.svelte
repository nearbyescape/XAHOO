<script lang="ts">
  // Taker buy vs sell volume over the last minute; the glowing pulse is the last 5 seconds.
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import { usd } from '../lib/format';
  export let b60 = 0; export let s60 = 0; export let b5 = 0; export let s5 = 0;
  const share = tweened(0.5, { duration: 600, easing: cubicOut });
  $: tot = b60 + s60;
  $: share.set(tot > 0 ? b60 / tot : 0.5);
  $: burst = b5 + s5 > 0 ? (b5 - s5) / (b5 + s5) : 0;
  $: strength = tot > 0 ? Math.min(1, ((b5 + s5) * 12) / tot) : 0;
</script>
<div class="flow" title="Taker buy vs sell volume, last 60 seconds">
  <span class="lab">Flow 60s</span>
  <span class="num b">{($share * 100).toFixed(0)}%</span>
  <div class="bar">
    <i class="buy" style="width:{$share * 100}%"></i>
    <i class="mid"></i>
    <i class="pulse" class:up={burst > 0} style="left:{50 + burst * 46}%; opacity:{0.2 + 0.8 * strength}; transform: translate(-50%, -50%) scale({0.6 + strength})"></i>
  </div>
  <span class="num s">{(100 - $share * 100).toFixed(0)}%</span>
  <span class="num net" class:up={b60 > s60} class:down={b60 < s60}>{usd(b60 - s60)}</span>
</div>
<style>
  .flow { display: grid; grid-template-columns: auto 30px 1fr 30px 62px; align-items: center; gap: 7px; padding: 6px 14px 12px; }
  .lab { font: 600 9px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); }
  .b { color: var(--up); font-size: 10.5px; text-align: right; } .s { color: var(--down); font-size: 10.5px; }
  .net { font-size: 10.5px; text-align: right; }
  .bar { position: relative; height: 5px; border-radius: 3px; background: rgba(var(--down-rgb), .55); }
  .buy { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px 0 0 3px; background: var(--up); }
  .mid { position: absolute; left: 50%; top: -3px; bottom: -3px; width: 1px; background: var(--text); opacity: .5; }
  .pulse { position: absolute; top: 50%; width: 8px; height: 8px; border-radius: 50%; background: var(--down); box-shadow: 0 0 10px var(--down); transition: left .5s ease, opacity .4s, transform .4s; }
  .pulse.up { background: var(--up); box-shadow: 0 0 10px var(--up); }
</style>
