<script lang="ts">
  // Direction symbol: green ↑ = UP, red ↓ = DOWN, grey – = NEUTRAL (within 2 points of 50%) or no tested edge.
  // When the direction changes the symbol pops in with a ripple; strong calls (55%+) gently bob.
  import { scale } from 'svelte/transition';
  import { backOut } from 'svelte/easing';
  import { conviction, dirOf } from '../lib/format';
  export let p = 0.5;
  export let show = true;
  export let size = 18;
  export let glow = true;
  export let lab: number | null | undefined = undefined;     // steady label from the server, when available
  $: d = show ? dirOf(p, lab) : 0;
  $: dir = d === 0 ? 'flat' : d > 0 ? 'up' : 'down';
  $: strong = glow && show && d !== 0 && conviction(p) === 2 && (d > 0) === (p >= 0.5);
</script>
<span class="dir {dir}" class:strong class:off={!show} style="width:{size}px; height:{size}px"
      aria-label={dir === 'up' ? `up ${(p * 100).toFixed(0)}%` : dir === 'down' ? `down ${((1 - p) * 100).toFixed(0)}%` : show ? 'neutral' : 'no edge'}>
  {#key dir}
    <span class="inner" in:scale={{ duration: 450, start: 0.35, easing: backOut }}>
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
    {#if dir !== 'flat' && show}<i class="ripple"></i>{/if}
  {/key}
</span>
<style>
  .dir { position: relative; display: inline-grid; place-items: center; flex: none; vertical-align: middle; border-radius: 50%;
    transition: background .4s, box-shadow .4s; }
  .inner { display: grid; place-items: center; width: 100%; height: 100%; }
  svg { width: 72%; height: 72%; }
  path { fill: none; stroke: #0a0d18; stroke-width: 3.2; stroke-linecap: round; stroke-linejoin: round; }
  .up { background: var(--up); }
  .down { background: var(--down); }
  .flat { background: rgba(148, 163, 214, .22); }
  .flat path { stroke: var(--muted); }
  .off { background: transparent; box-shadow: inset 0 0 0 1px var(--line2); }
  .off path { stroke: var(--faint); }
  /* ripple once when the direction changes */
  .ripple { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; animation: ripple .9s ease-out forwards; }
  .up .ripple { box-shadow: 0 0 0 2px var(--up); } .down .ripple { box-shadow: 0 0 0 2px var(--down); }
  @keyframes ripple { from { transform: scale(1); opacity: .9; } to { transform: scale(2.1); opacity: 0; } }
  /* strong calls: glow and a gentle bob in the arrow's direction */
  .strong.up { box-shadow: 0 0 10px rgba(var(--up-rgb), .7); animation: glowUp 2.2s ease-in-out infinite; }
  .strong.down { box-shadow: 0 0 10px rgba(var(--down-rgb), .7); animation: glowDown 2.2s ease-in-out infinite; }
  .strong.up svg { animation: bobUp 1.6s ease-in-out infinite; }
  .strong.down svg { animation: bobDown 1.6s ease-in-out infinite; }
  @keyframes bobUp { 0%, 100% { transform: translateY(1px); } 50% { transform: translateY(-2px); } }
  @keyframes bobDown { 0%, 100% { transform: translateY(-1px); } 50% { transform: translateY(2px); } }
  @keyframes glowUp { 0%, 100% { box-shadow: 0 0 4px rgba(var(--up-rgb), .5); } 50% { box-shadow: 0 0 14px rgba(var(--up-rgb), .9); } }
  @keyframes glowDown { 0%, 100% { box-shadow: 0 0 4px rgba(var(--down-rgb), .5); } 50% { box-shadow: 0 0 14px rgba(var(--down-rgb), .9); } }
</style>
