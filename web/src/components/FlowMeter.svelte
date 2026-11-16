<script lang="ts">
  // Buy vs sell (taker) volume over the last minute; the pulse shows the last 5 seconds.
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import { usd } from '../lib/format';
  export let b60 = 0; export let s60 = 0; export let b5 = 0; export let s5 = 0;
  const share = tweened(0.5, { duration: 600, easing: cubicOut });
  $: tot = b60 + s60;
  $: share.set(tot > 0 ? b60 / tot : 0.5);
  $: burst = b5 + s5 > 0 ? (b5 - s5) / (b5 + s5) : 0;
  $: strength = tot > 0 ? Math.min(1, ((b5 + s5) * 12) / tot) : 0;       // last 5s vs the minute's average pace
</script>
<div class="flow" title="Taker buy vs sell volume, last 60 s">
  <div class="bar">
    <i class="b" style="width:{$share * 100}%"></i>
    <i class="mid"></i>
    <i class="pulse" class:up={burst > 0} style="left:{50 + burst * 46}%; opacity:{0.25 + 0.75 * strength}; transform: translate(-50%, -50%) scale({0.7 + strength})"></i>
  </div>
  <div class="lbl num"><span class="up">{($share * 100).toFixed(0)}%</span><span class="dim">{usd(b60 - s60)}</span><span class="down">{(100 - $share * 100).toFixed(0)}%</span></div>
</div>
<style>
  .flow { width: 150px; }
  .bar { position: relative; height: 8px; background: color-mix(in srgb, var(--down) 55%, #000); overflow: visible; }
  .b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--up); }
  .mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--text); opacity: .55; }
  .pulse { position: absolute; top: 50%; width: 9px; height: 9px; border-radius: 50%; background: var(--down); box-shadow: 0 0 10px var(--down); transition: left .5s ease, opacity .4s, transform .4s; }
  .pulse.up { background: var(--up); box-shadow: 0 0 10px var(--up); }
  .lbl { display: flex; justify-content: space-between; font-size: 10px; margin-top: 3px; }
</style>
