<script lang="ts">
  import Arrow from './Arrow.svelte';
  // One horizon: diverging bar from 50%, the probability, the expected move and a trail of the last 90 minutes.
  import { onMount, onDestroy } from 'svelte';
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import type { Fc } from '../lib/types';
  import { probColor, lean, FULL, HORIZON_MIN } from '../lib/format';
  import { now } from '../lib/store';
  export let h: string;
  export let fc: Fc | undefined;
  export let trail: number[] = [];
  export let changedAt = 0;
  export let forecastTs = 0;
  let canvas: HTMLCanvasElement;
  let flash = false, ft: ReturnType<typeof setTimeout>;
  let ring = 0, timer: ReturnType<typeof setInterval>;
  const fill = tweened(0, { duration: 700, easing: cubicOut });
  $: show = !!fc && fc.show;
  $: p = fc ? fc.p : 0.5;
  $: fill.set(show ? lean(p) : 0);
  $: col = probColor(p);
  $: if (changedAt) { flash = false; clearTimeout(ft); requestAnimationFrame(() => (flash = true)); ft = setTimeout(() => (flash = false), 1400); }
  $: draw(trail, show);
  function draw(r: number[], s: boolean) {
    if (!canvas) return;
    const dpr = devicePixelRatio || 1, W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const c = canvas.getContext('2d')!;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    c.strokeStyle = 'rgba(148,163,214,.16)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(0, H / 2 + 0.5); c.lineTo(W, H / 2 + 0.5); c.stroke();
    if (!s || r.length < 2) return;
    const y = (v: number) => H / 2 - Math.max(-1, Math.min(1, (v - 0.5) / (FULL * 1.2))) * (H / 2 - 1);
    c.beginPath();
    r.forEach((v, i) => { const x = (i / (r.length - 1)) * W; i ? c.lineTo(x, y(v)) : c.moveTo(x, y(v)); });
    c.strokeStyle = probColor(r[r.length - 1], 0.9); c.lineWidth = 1.2; c.stroke();
  }
  const short = h === '1m' || h === '5m';
  onMount(() => {
    draw(trail, show);
    if (short) timer = setInterval(() => {
      ring = forecastTs ? Math.max(0, Math.min(1, (now() - forecastTs) / (HORIZON_MIN[h] * 60))) : 0;
    }, 500);
  });
  onDestroy(() => { clearInterval(timer); clearTimeout(ft); });
</script>
<div class="hr" class:off={!show} class:weak={show && fc?.tier === 1} class:flash>
  <span class="h">
    {#if short && show}<svg class="ring" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" class="bg" /><circle cx="8" cy="8" r="6" class="fg" style="stroke-dashoffset:{37.7 * ring}" /></svg>{/if}
    {h}
  </span>
  <span class="bar">
    <i class="mid"></i>
    {#if show}
      <i class="fill" style="width:{Math.abs($fill) * 50}%; {$fill >= 0 ? 'left:50%' : 'right:50%'}; background:{$fill >= 0
        ? `linear-gradient(90deg, rgba(var(--up-rgb),.15), ${col})` : `linear-gradient(270deg, rgba(var(--down-rgb),.15), ${col})`}; box-shadow: 0 0 12px {probColor(p, .45)}"></i>
    {/if}
  </span>
  {#if show && fc}
    <span class="v num" style="color:{col}"><Arrow {p} lab={fc?.lab} size={15} glow={false} />{((p >= 0.5 ? p : 1 - p) * 100).toFixed(0)}<small>%</small></span>
  {:else}
    <span class="v none">no edge</span>
  {/if}
  <span class="mv num" class:faint={!fc?.tradable} title={fc?.tradable ? 'Expected move (68% range)' : 'Expected move is smaller than typical trading costs'}>{fc ? `±${(fc.move_bp / 100).toFixed(fc.move_bp < 100 ? 2 : 1)}%` : '—'}</span>
  <canvas bind:this={canvas}></canvas>
</div>
<style>
  .hr { position: relative; display: grid; grid-template-columns: 38px minmax(60px, 1fr) 58px 50px 40px; align-items: center; gap: 8px; height: 25px; padding: 0 14px; }
  .hr.flash::before { content: ""; position: absolute; inset: 1px 6px; border-radius: 6px; background: rgba(139, 124, 255, .16); box-shadow: 0 0 0 1px rgba(139, 124, 255, .55); animation: fl 1.4s ease-out forwards; pointer-events: none; }
  @keyframes fl { from { opacity: 1; } to { opacity: 0; } }
  .h { display: flex; align-items: center; gap: 4px; font: 600 11px var(--mono); color: var(--muted); }
  .ring { width: 11px; height: 11px; transform: rotate(-90deg); flex: none; }
  .ring circle { fill: none; stroke-width: 2.6; }
  .ring .bg { stroke: var(--line2); }
  .ring .fg { stroke: var(--accent); stroke-dasharray: 37.7; transition: stroke-dashoffset .5s linear; }
  .bar { position: relative; height: 7px; border-radius: 4px; background: rgba(148, 163, 214, .08); overflow: hidden; }
  .bar .mid { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--line3); }
  .bar .fill { position: absolute; top: 0; bottom: 0; border-radius: 4px; transition: background .5s; }
  .v { display: inline-flex; align-items: center; justify-content: flex-end; gap: 4px; font-size: 13px; font-weight: 700; text-align: right; transition: color .5s; white-space: nowrap; }
  .v small { font-size: 10px; font-weight: 500; opacity: .75; }
  .none { font: 500 10px var(--sans); color: var(--faint); text-align: right; letter-spacing: .3px; }
  .mv { font-size: 10.5px; color: var(--muted); text-align: right; }
  canvas { width: 40px; height: 16px; }
  .off .bar { background: repeating-linear-gradient(135deg, rgba(148,163,214,.07) 0 3px, transparent 3px 6px); }
  .off .h { color: var(--faint); }
  .weak .v, .weak .bar .fill { opacity: .7; }
</style>
