<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { Fc } from '../lib/types';
  import { probColor, probBg, HORIZON_MIN, FULL } from '../lib/format';
  import { now } from '../lib/store';
  export let h: string;
  export let fc: Fc | undefined;
  export let ribbon: number[] = [];
  export let changedAt = 0;
  export let forecastTs = 0;
  let canvas: HTMLCanvasElement;
  let flash = false, ft: ReturnType<typeof setTimeout>;
  let ring = 0, timer: ReturnType<typeof setInterval>;
  $: show = !!fc && fc.show;
  $: p = fc ? fc.p : 0.5;
  $: up = p >= 0.5;
  $: conf = Math.min(1, Math.abs(p - 0.5) / FULL);
  $: if (changedAt) { flash = false; clearTimeout(ft); requestAnimationFrame(() => (flash = true)); ft = setTimeout(() => (flash = false), 1200); }
  $: draw(ribbon, show);
  function draw(r: number[], _s: boolean) {
    if (!canvas) return;
    const w = (canvas.width = canvas.clientWidth * devicePixelRatio), hgt = (canvas.height = canvas.clientHeight * devicePixelRatio);
    const c = canvas.getContext('2d')!;
    c.clearRect(0, 0, w, hgt);
    if (!show || r.length < 2) return;
    const y = (v: number) => hgt / 2 - ((v - 0.5) / (FULL * 1.25)) * (hgt / 2);
    c.beginPath();
    r.forEach((v, i) => { const x = (i / (r.length - 1)) * w; i ? c.lineTo(x, y(v)) : c.moveTo(x, y(v)); });
    c.strokeStyle = probColor(r[r.length - 1], 0.55); c.lineWidth = devicePixelRatio; c.stroke();
    c.lineTo(w, hgt / 2); c.lineTo(0, hgt / 2); c.closePath();
    c.fillStyle = probColor(r[r.length - 1], 0.1); c.fill();
  }
  // countdown ring: time left in the short horizons' window
  const short = h === '1m' || h === '5m';
  onMount(() => {
    draw(ribbon, show);
    if (short) timer = setInterval(() => {
      const span = HORIZON_MIN[h] * 60;
      ring = forecastTs ? Math.max(0, Math.min(1, (now() - forecastTs) / span)) : 0;
    }, 500);
  });
  onDestroy(() => { clearInterval(timer); clearTimeout(ft); });
</script>
<div class="cell" class:noedge={!show} class:weak={show && fc && fc.tier === 1} class:flash style={show ? `background:${probBg(p)}` : ''}>
  <canvas bind:this={canvas}></canvas>
  {#if show && fc}
    <div class="main num" style="color:{probColor(p)}">
      <span class="arrow">{up ? '▲' : '▼'}</span>{((up ? p : 1 - p) * 100).toFixed(0)}<span class="pc">%</span>
    </div>
    <div class="sub num"><span class:dim={!fc.tradable} title={fc.tradable ? 'expected move (68% band)' : 'expected move is smaller than typical trading costs'}>±{(fc.move_bp / 100).toFixed(fc.move_bp < 100 ? 2 : 1)}%</span>{#if fc.tier === 1}<span class="tag">weak</span>{/if}</div>
    <i class="conf" style="width:{conf * 100}%; background:{probColor(p)}"></i>
  {:else}
    <div class="main none">· · ·</div>
    <div class="sub num dim">{#if fc}±{(fc.move_bp / 100).toFixed(fc.move_bp < 100 ? 2 : 1)}%{:else}—{/if}<span class="tag">no edge</span></div>
  {/if}
  {#if short && show}
    <svg class="ring" viewBox="0 0 20 20"><circle cx="10" cy="10" r="7" class="bg" /><circle cx="10" cy="10" r="7" class="fg" style="stroke-dashoffset:{44 * ring}" /></svg>
  {/if}
</div>
<style>
  .cell { position: relative; height: 100%; min-width: 92px; padding: 9px 10px 8px; border-left: 1px solid var(--line); overflow: hidden; transition: background .8s ease; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .main { position: relative; font-size: 21px; font-weight: 700; line-height: 1.1; letter-spacing: -.5px; transition: color .6s ease; }
  .arrow { font-size: 11px; margin-right: 4px; vertical-align: 3px; }
  .pc { font-size: 12px; font-weight: 500; margin-left: 1px; opacity: .8; }
  .sub { position: relative; font-size: 10px; color: var(--text); opacity: .85; margin-top: 3px; display: flex; gap: 6px; align-items: center; }
  .tag { font-size: 8.5px; letter-spacing: .8px; text-transform: uppercase; color: var(--dim); border: 1px solid var(--line2); padding: 0 3px; }
  .conf { position: absolute; left: 0; bottom: 0; height: 2px; transition: width .8s ease, background .6s; }
  .none { color: var(--dimmer); font-weight: 400; letter-spacing: 1px; }
  .noedge { background: repeating-linear-gradient(135deg, transparent 0 6px, rgba(255,255,255,.012) 6px 12px); }
  .weak .main { opacity: .72; }
  .flash::after { content: ""; position: absolute; inset: 0; border: 1px solid var(--amber); animation: fl 1.2s ease-out forwards; pointer-events: none; }
  @keyframes fl { from { opacity: 1; box-shadow: inset 0 0 18px rgba(245,165,36,.35); } to { opacity: 0; box-shadow: none; } }
  .ring { position: absolute; right: 5px; top: 5px; width: 14px; height: 14px; transform: rotate(-90deg); }
  .ring circle { fill: none; stroke-width: 2.4; }
  .ring .bg { stroke: var(--line2); }
  .ring .fg { stroke: var(--amber); stroke-dasharray: 44; transition: stroke-dashoffset .5s linear; }
</style>
