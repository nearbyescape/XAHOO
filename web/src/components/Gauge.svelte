<script lang="ts" context="module">
  let uid = 0;
</script>
<script lang="ts">
  // Direction dial. Thick needle + lit arc: blend of the 15m–4h probabilities. Thin needle: the 1–5 minute push.
  import { spring } from 'svelte/motion';
  import { probColor } from '../lib/format';
  export let slow = 0.5;
  export let fast = 0.5;
  export let hasFast = true;
  export let size = 128;
  const id = `g${++uid}`;
  const sAng = spring(0, { stiffness: 0.05, damping: 0.45 });
  const fAng = spring(0, { stiffness: 0.12, damping: 0.32 });
  const toAngle = (p: number) => Math.max(-88, Math.min(88, ((p - 0.5) / 0.08) * 88));   // ±8 points = full scale
  $: sAng.set(toAngle(slow));
  $: fAng.set(toAngle(fast));
  const cx = 60, cy = 60, R = 48;
  const pt = (a: number, r = R) => [cx + r * Math.sin((a * Math.PI) / 180), cy - r * Math.cos((a * Math.PI) / 180)];
  const arc = (a0: number, a1: number, r = R) => {
    const [x0, y0] = pt(a0, r), [x1, y1] = pt(a1, r);
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };
  $: lit = Math.abs($sAng) < 0.5 ? '' : $sAng > 0 ? arc(0, $sAng) : arc($sAng, 0);
  $: col = probColor(slow);
</script>
<svg viewBox="0 0 120 66" style="width:{size}px" class="gauge" aria-label="direction dial">
  <defs>
    <linearGradient id="{id}t" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0" stop-color="rgb(var(--down-rgb))" stop-opacity=".55" />
      <stop offset=".5" stop-color="rgb(var(--neutral-rgb))" stop-opacity=".18" />
      <stop offset="1" stop-color="rgb(var(--up-rgb))" stop-opacity=".55" />
    </linearGradient>
    <filter id="{id}f" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" /></filter>
  </defs>
  <path d={arc(-90, 90)} stroke="url(#{id}t)" class="track" />
  {#each [-90, -45, 0, 45, 90] as a}
    {@const [x0, y0] = pt(a, R - 8)}{@const [x1, y1] = pt(a, R - 5)}
    <line x1={x0} y1={y0} x2={x1} y2={y1} class="tick" />
  {/each}
  {#if lit}
    <path d={lit} stroke={col} class="lit glow" filter="url(#{id}f)" />
    <path d={lit} stroke={col} class="lit" />
  {/if}
  {#if hasFast}
    <line x1={cx} y1={cy} x2={cx} y2={cy - R + 12} transform="rotate({$fAng} {cx} {cy})" class="fast" style="stroke:{probColor(fast, .85)}" />
  {/if}
  <line x1={cx} y1={cy} x2={cx} y2={cy - R + 6} transform="rotate({$sAng} {cx} {cy})" class="slow" style="stroke:{col}" />
  <circle cx={cx} cy={cy} r="4.2" class="hub" style="stroke:{col}" />
</svg>
<style>
  .gauge { display: block; height: auto; overflow: visible; }
  .track { fill: none; stroke-width: 7; stroke-linecap: round; }
  .lit { fill: none; stroke-width: 7; stroke-linecap: round; }
  .glow { opacity: .7; }
  .tick { stroke: var(--line3); stroke-width: 1.2; }
  .slow { stroke-width: 3; stroke-linecap: round; }
  .fast { stroke-width: 1.4; stroke-linecap: round; stroke-dasharray: 2.5 2.5; }
  .hub { fill: var(--panel-solid); stroke-width: 2; }
</style>
