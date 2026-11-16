<script lang="ts">
  // Last 3 hours of price with the nearest resistance (amber) and support (azure) drawn as dashed lines.
  import { onMount } from 'svelte';
  import type { Levels } from '../lib/types';
  export let data: number[] = [];
  export let price: number | null = null;
  export let levels: Levels | undefined;
  let canvas: HTMLCanvasElement;
  let dot = { x: 0, y: 0, show: false, up: true };
  const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  $: draw(data, price, levels);
  function draw(..._: unknown[]) {
    if (!canvas) return;
    const dpr = devicePixelRatio || 1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const c = canvas.getContext('2d')!;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const pts = price != null ? [...data, price] : data;
    if (pts.length < 2) { dot.show = false; return; }
    let lo = Math.min(...pts), hi = Math.max(...pts);
    const span0 = hi - lo || hi * 0.001;
    const R = levels?.resistance?.[0]?.price, S = levels?.support?.[0]?.price;
    // bring the nearest levels into view when they are reasonably close
    if (R && R - hi < span0 * 0.9) hi = Math.max(hi, R);
    if (S && lo - S < span0 * 0.9) lo = Math.min(lo, S);
    const pad = (hi - lo) * 0.12 || 1;
    lo -= pad; hi += pad;
    const X = (i: number) => (i / (pts.length - 1)) * (W - 30);
    const Y = (v: number) => H - ((v - lo) / (hi - lo)) * H;
    const up = pts[pts.length - 1] >= pts[0];
    const rgb = up ? css('--up-rgb') : css('--down-rgb');
    // levels
    for (const [v, col, tag] of [[R, css('--res'), 'R'], [S, css('--sup'), 'S']] as [number | undefined, string, string][]) {
      if (!v || v > hi || v < lo) continue;
      const y = Math.round(Y(v)) + 0.5;
      c.strokeStyle = col; c.globalAlpha = 0.75; c.setLineDash([3, 3]); c.lineWidth = 1;
      c.beginPath(); c.moveTo(0, y); c.lineTo(W - 22, y); c.stroke();
      c.setLineDash([]); c.globalAlpha = 1;
      c.fillStyle = col; c.font = '600 9px Inter, sans-serif'; c.textBaseline = 'middle';
      c.fillText(tag, W - 16, y);
    }
    // area + line
    const g = c.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, `rgba(${rgb}, .28)`); g.addColorStop(1, `rgba(${rgb}, 0)`);
    c.beginPath();
    pts.forEach((v, i) => (i ? c.lineTo(X(i), Y(v)) : c.moveTo(X(i), Y(v))));
    c.lineTo(X(pts.length - 1), H); c.lineTo(0, H); c.closePath();
    c.fillStyle = g; c.fill();
    c.beginPath();
    pts.forEach((v, i) => (i ? c.lineTo(X(i), Y(v)) : c.moveTo(X(i), Y(v))));
    c.strokeStyle = `rgba(${rgb}, .95)`; c.lineWidth = 1.5; c.lineJoin = 'round'; c.stroke();
    dot = { x: X(pts.length - 1), y: Y(pts[pts.length - 1]), show: true, up };
  }
  onMount(() => { draw(); const ro = new ResizeObserver(() => draw()); ro.observe(canvas); return () => ro.disconnect(); });
</script>
<div class="spark">
  <canvas bind:this={canvas}></canvas>
  {#if dot.show}<i class="dot" class:dn={!dot.up} style="left:{dot.x}px; top:{dot.y}px"></i>{/if}
</div>
<style>
  .spark { position: relative; width: 100%; height: 100%; }
  canvas { width: 100%; height: 100%; display: block; }
  .dot { position: absolute; width: 6px; height: 6px; margin: -3px 0 0 -3px; border-radius: 50%; background: var(--up); transition: top .4s ease; }
  .dot::after { content: ""; position: absolute; inset: -5px; border-radius: 50%; border: 1px solid var(--up); animation: ping 1.8s ease-out infinite; }
  .dot.dn { background: var(--down); } .dot.dn::after { border-color: var(--down); }
  @keyframes ping { from { transform: scale(.4); opacity: .9; } to { transform: scale(1.6); opacity: 0; } }
</style>
