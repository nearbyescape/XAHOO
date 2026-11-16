<script lang="ts">
  // Direction gauge. Thick needle: blend of the longer horizons. Thin fast needle: 1m–5m push.
  import { spring } from 'svelte/motion';
  import { probColor } from '../lib/format';
  export let slow = 0.5;
  export let fast = 0.5;
  export let hasFast = true;
  const sAng = spring(0, { stiffness: 0.06, damping: 0.5 });
  const fAng = spring(0, { stiffness: 0.12, damping: 0.35 });
  const toAngle = (p: number) => Math.max(-80, Math.min(80, ((p - 0.5) / 0.08) * 80));   // ±8 points = full scale
  $: sAng.set(toAngle(slow));
  $: fAng.set(toAngle(fast));
  const arc = (a0: number, a1: number, r: number) => {
    const pt = (a: number) => [50 + r * Math.sin((a * Math.PI) / 180), 46 - r * Math.cos((a * Math.PI) / 180)];
    const [x0, y0] = pt(a0), [x1, y1] = pt(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
</script>
<svg viewBox="0 0 100 52" class="needle" aria-label="direction gauge">
  <path d={arc(-80, -8, 38)} class="track dn" />
  <path d={arc(8, 80, 38)} class="track up" />
  <path d={arc(-8, 8, 38)} class="track mid" />
  {#each [-80, -40, 0, 40, 80] as a}
    <line x1="50" y1="5" x2="50" y2="9" transform="rotate({a} 50 46)" class="tick" />
  {/each}
  {#if hasFast}
    <line x1="50" y1="46" x2="50" y2="13" transform="rotate({$fAng} 50 46)" class="fast" style="stroke:{probColor(fast, 0.9)}" />
  {/if}
  <line x1="50" y1="46" x2="50" y2="17" transform="rotate({$sAng} 50 46)" class="slow" style="stroke:{probColor(slow)}" />
  <circle cx="50" cy="46" r="3.2" class="hub" />
</svg>
<style>
  .needle { width: 92px; height: 48px; display: block; }
  .track { fill: none; stroke-width: 3; stroke-linecap: round; }
  .track.up { stroke: color-mix(in srgb, var(--up) 30%, transparent); }
  .track.dn { stroke: color-mix(in srgb, var(--down) 30%, transparent); }
  .track.mid { stroke: var(--line2); }
  .tick { stroke: var(--dimmer); stroke-width: 1; }
  .slow { stroke-width: 2.6; stroke-linecap: round; }
  .fast { stroke-width: 1; stroke-linecap: round; stroke-dasharray: 2 2; }
  .hub { fill: var(--panel2); stroke: var(--line2); }
</style>
