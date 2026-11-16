<script lang="ts">
  // Direction symbol: green ↑ = UP, red ↓ = DOWN, grey – = NEUTRAL (within 2 points of 50%) or no tested edge.
  import { conviction } from '../lib/format';
  export let p = 0.5;
  export let show = true;
  export let size = 18;
  export let glow = true;
  $: dir = !show || conviction(p) === 0 ? 'flat' : p >= 0.5 ? 'up' : 'down';
  $: strong = glow && show && conviction(p) === 2;
</script>
<span class="dir {dir}" class:strong class:off={!show} style="width:{size}px; height:{size}px"
      aria-label={dir === 'up' ? `up ${(p * 100).toFixed(0)}%` : dir === 'down' ? `down ${((1 - p) * 100).toFixed(0)}%` : show ? 'neutral' : 'no edge'}>
  <svg viewBox="0 0 24 24">
    {#if dir === 'up'}
      <path d="M12 19V6 M6 11.5L12 5.5L18 11.5" />
    {:else if dir === 'down'}
      <path d="M12 5v13 M6 12.5L12 18.5L18 12.5" />
    {:else}
      <path d="M7 12H17" />
    {/if}
  </svg>
</span>
<style>
  .dir { display: inline-grid; place-items: center; flex: none; vertical-align: middle; border-radius: 50%; transition: background .4s, box-shadow .4s; }
  svg { width: 72%; height: 72%; }
  path { fill: none; stroke: #0a0d18; stroke-width: 3.2; stroke-linecap: round; stroke-linejoin: round; }
  .up { background: var(--up); }
  .down { background: var(--down); }
  .flat { background: rgba(148, 163, 214, .22); }
  .flat path { stroke: var(--muted); }
  .off { background: transparent; box-shadow: inset 0 0 0 1px var(--line2); }
  .off path { stroke: var(--faint); }
  .strong.up { box-shadow: 0 0 10px rgba(var(--up-rgb), .7); }
  .strong.down { box-shadow: 0 0 10px rgba(var(--down-rgb), .7); }
</style>
