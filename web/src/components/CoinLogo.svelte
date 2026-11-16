<script lang="ts">
  // Market logo in a styled ring: coin icons from the open-source cryptocurrency-icons set (CC0), drawn gold /
  // silver bars for XAU / XAG. Soft glow in the market's colour; a plain ticker badge if an icon fails to load.
  import { BADGE } from '../lib/format';
  export let sym: string;
  export let short = '';
  export let size = 34;
  export let glow = true;
  let failed = false;
  $: file = `/icons/coins/${sym.replace(/USDT$/, '').toLowerCase()}.svg`;
  $: c = BADGE[sym] || ['#8b7cff', '#38c6f4'];
</script>
<span class="logo" class:glow style="width:{size}px; height:{size}px; --c1:{c[0]}; --c2:{c[1]}" title={short || sym}>
  {#if !failed}
    <img src={file} alt={short} width={size - 6} height={size - 6} on:error={() => (failed = true)} />
  {:else}
    <b style="font-size:{Math.max(8, size * (short.length > 3 ? 0.24 : 0.3))}px">{short}</b>
  {/if}
</span>
<style>
  .logo { position: relative; flex: none; display: grid; place-items: center; border-radius: 50%;
    background: radial-gradient(circle at 30% 25%, rgba(255,255,255,.14), rgba(10,13,24,.9) 70%);
    box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--c1) 70%, transparent); transition: transform .25s ease, box-shadow .3s ease; }
  .logo::before { content: ""; position: absolute; inset: -2px; border-radius: 50%; padding: 1.5px;
    background: conic-gradient(from 210deg, var(--c1), var(--c2), transparent 60%, var(--c1));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude; opacity: .9; }
  .glow { box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--c1) 70%, transparent), 0 0 14px -2px color-mix(in srgb, var(--c1) 55%, transparent); }
  img { display: block; border-radius: 50%; filter: drop-shadow(0 1px 2px rgba(0,0,0,.45)); }
  b { font-family: var(--sans); font-weight: 800; color: #0b0e1a; width: 100%; height: 100%; border-radius: 50%; display: grid; place-items: center;
    background: linear-gradient(135deg, var(--c1), var(--c2)); }
  :global(:hover) > .logo, .logo:hover { transform: scale(1.06); }
</style>
