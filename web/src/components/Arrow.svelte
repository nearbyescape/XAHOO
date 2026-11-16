<script lang="ts">
  // Direction arrow. Flat (→) at 50%; tilts toward ↑ or ↓ as the probability leans, fully vertical at
  // about ±7 points (the range calibrated probabilities actually span). Springs to new angles.
  import { spring } from 'svelte/motion';
  import { probColor, lean } from '../lib/format';
  export let p = 0.5;
  export let show = true;
  export let size = 18;
  export let glow = true;
  const ang = spring(0, { stiffness: 0.08, damping: 0.45 });
  $: ang.set(show ? -lean(p) * 90 : 0);
  $: col = show ? probColor(p) : 'var(--faint)';
  $: strong = glow && show && Math.abs(lean(p)) > 0.6;
</script>
<span class="arw" class:strong style="width:{size}px; height:{size}px; --c:{col}" aria-label={show ? `${p >= 0.5 ? 'up' : 'down'} ${(Math.max(p, 1 - p) * 100).toFixed(0)}%` : 'no edge'}>
  {#if show}
    <svg viewBox="0 0 24 24" style="transform: rotate({$ang}deg)">
      <circle cx="12" cy="12" r="11" class="bg" />
      <path d="M5 12 H17 M12.5 7 L18 12 L12.5 17" class="ar" />
    </svg>
  {:else}
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" class="bg off" /><path d="M8 12 H16" class="ar off" /></svg>
  {/if}
</span>
<style>
  .arw { display: inline-grid; place-items: center; flex: none; vertical-align: middle; }
  svg { width: 100%; height: 100%; overflow: visible; }
  .bg { fill: color-mix(in srgb, var(--c) 16%, transparent); stroke: color-mix(in srgb, var(--c) 45%, transparent); stroke-width: 1; transition: fill .6s, stroke .6s; }
  .bg.off { fill: transparent; stroke: var(--line2); stroke-dasharray: 2 2; }
  .ar { fill: none; stroke: var(--c); stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; transition: stroke .6s; }
  .ar.off { stroke: var(--faint); stroke-width: 2; }
  .strong svg { filter: drop-shadow(0 0 4px var(--c)); animation: breathe 2.4s ease-in-out infinite; }
  @keyframes breathe { 0%, 100% { filter: drop-shadow(0 0 2px var(--c)); } 50% { filter: drop-shadow(0 0 7px var(--c)); } }
</style>
