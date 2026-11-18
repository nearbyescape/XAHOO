<script lang="ts">
  // Every timeframe for the chosen market: steady direction, probability bar, expected price range (68%),
  // the strongest reason and the last 2 hours of the probability. Click a row to explain it in the chart and panel.
  import type { Market } from '../lib/types';
  import { px, probColor, lean, biasWord, dirOf, HORIZON_MIN } from '../lib/format';
  import { fh } from '../lib/store';
  import Arrow from './Arrow.svelte';
  export let m: Market;
  $: fc = m.forecast?.h || {};
  $: hs = Object.keys(HORIZON_MIN).filter(h => fc[h]);
  const TRAIL = 120;
  function trail(node: HTMLCanvasElement, data: number[]) {
    const draw = (d: number[]) => {
      const dpr = devicePixelRatio || 1, W = node.clientWidth, H = node.clientHeight;
      node.width = W * dpr; node.height = H * dpr;
      const c = node.getContext('2d')!;
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.clearRect(0, 0, W, H);
      c.strokeStyle = 'rgba(148,163,214,.22)'; c.setLineDash([2, 3]);
      c.beginPath(); c.moveTo(0, H / 2); c.lineTo(W, H / 2); c.stroke(); c.setLineDash([]);
      if (d.length < 2) return;
      const y = (p: number) => H / 2 - Math.max(-1, Math.min(1, (p - 0.5) / 0.08)) * (H / 2 - 2);
      const x = (i: number) => W - (d.length - 1 - i) * (W / (TRAIL - 1));
      for (const [sign, col] of [[1, 'rgba(46,230,168,'], [-1, 'rgba(255,92,138,']] as [number, string][]) {
        c.save(); c.beginPath();
        if (sign > 0) c.rect(0, 0, W, H / 2); else c.rect(0, H / 2, W, H / 2);
        c.clip();
        c.beginPath(); c.moveTo(x(0), H / 2);
        d.forEach((p, i) => c.lineTo(x(i), y(p)));
        c.lineTo(x(d.length - 1), H / 2); c.closePath();
        c.fillStyle = col + '.16)'; c.fill();
        c.beginPath(); d.forEach((p, i) => (i ? c.lineTo(x(i), y(p)) : c.moveTo(x(i), y(p))));
        c.strokeStyle = col + '.95)'; c.lineWidth = 1.5; c.stroke();
        c.restore();
      }
      const last = d[d.length - 1];
      c.fillStyle = probColor(last); c.beginPath(); c.arc(x(d.length - 1), y(last), 2.6, 0, Math.PI * 2); c.fill();
    };
    draw(data);
    return { update: draw };
  }
</script>
<section class="tf panel">
  <div class="ph">All timeframes · {m.short} <span class="r">click a row to explain it · trail = last 2 hours</span></div>
  <div class="hd"><span>Time</span><span>Direction</span><span>Probability</span><span class="r">Expected range (68%)</span><span>Main reason</span><span class="r">Last 2h</span></div>
  <div class="rows">
    {#each hs as h (h)}
      {@const x = fc[h]}{@const d = dirOf(x.p, x.lab)}{@const tr = m.ribbon.slice(-TRAIL).map(r => r[1][h]).filter(v => v != null)}
      <button class="row" class:on={$fh === h} class:off={!x.show} on:click={() => fh.set(h)}>
        <span class="h num">{h}</span>
        {#if x.show}
          <span class="dw" class:up={d > 0} class:down={d < 0}><Arrow p={x.p} lab={x.lab} size={18} glow={false} />{biasWord(x.p, x.lab)}</span>
          <span class="pb"><span class="bar"><i class="mid"></i><i class="fill" style="width:{Math.abs(lean(x.p)) * 50}%; {x.p >= 0.5 ? 'left:50%' : 'right:50%'}; background:{probColor(x.p)}"></i></span>
            <b class="num" style="color:{probColor(x.p)}">{((x.p >= 0.5 ? x.p : 1 - x.p) * 100).toFixed(1)}%</b></span>
        {:else}
          <span class="dw ne">NO EDGE</span><span class="pb ne">not shown: no tested skill</span>
        {/if}
        <span class="rg num">{px(x.lo68, m.digits)} – {px(x.hi68, m.digits)}<small>±{(x.band68 * 100).toFixed(2)}%</small></span>
        <span class="why">{#if x.show && x.reasons?.length}<i class:up={x.reasons[0].push > 0} class:down={x.reasons[0].push < 0}>{x.reasons[0].push > 0 ? '↑' : '↓'}</i>{x.reasons[0].t}{:else}<span class="faint">—</span>{/if}</span>
        <canvas use:trail={x.show ? tr : []}></canvas>
      </button>
    {/each}
  </div>
</section>
<style>
  .tf { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .hd, .row { display: grid; grid-template-columns: 34px 128px minmax(140px, 1fr) 150px minmax(170px, 1.6fr) 120px; gap: 12px; align-items: center; }
  .hd { padding: 0 16px 4px; font: 600 9.5px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); }
  .hd .r, .rg { text-align: right; }
  .rows { flex: 1; overflow-y: auto; padding: 0 8px 8px; display: flex; flex-direction: column; gap: 2px; min-height: 0; }
  .row { padding: 4px 8px; min-height: 30px; border: 0; border-radius: 9px; background: transparent; text-align: left; transition: background .2s; }
  .row:hover { background: rgba(148,163,214,.06); }
  .row.on { background: linear-gradient(90deg, rgba(139,124,255,.16), rgba(139,124,255,.03)); box-shadow: inset 3px 0 var(--accent); }
  .h { font-size: 12px; font-weight: 700; color: var(--muted); }
  .dw { display: inline-flex; align-items: center; gap: 7px; font: 800 11px var(--sans); letter-spacing: 1px; color: var(--muted); white-space: nowrap; }
  .dw.up { color: var(--up); } .dw.down { color: var(--down); } .dw.ne { color: var(--faint); font-weight: 600; }
  .pb { display: flex; align-items: center; gap: 10px; }
  .pb.ne { font-size: 10.5px; color: var(--faint); }
  .bar { position: relative; flex: 1; height: 7px; border-radius: 4px; background: rgba(148,163,214,.08); overflow: hidden; }
  .bar .mid { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--line3); }
  .bar .fill { position: absolute; top: 0; bottom: 0; border-radius: 4px; transition: width .7s cubic-bezier(.2,.8,.2,1), background .5s; }
  .pb b { font-size: 13.5px; min-width: 74px; text-align: right; transition: color .5s; }
  .rg { font-size: 11.5px; color: var(--text); display: flex; flex-direction: column; align-items: flex-end; line-height: 1.2; }
  .rg small { font-size: 9.5px; color: var(--faint); }
  .why { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .why i { font-style: normal; font-weight: 800; margin-right: 6px; } .why i.up { color: var(--up); } .why i.down { color: var(--down); }
  canvas { width: 120px; height: 24px; }
  .off .h { color: var(--faint); }
  @media (max-width: 1300px) { .hd, .row { grid-template-columns: 36px 130px minmax(120px, 1fr) 150px 110px; } .why, .hd span:nth-child(5) { display: none; } }
  @media (max-width: 700px) { .hd, .row { grid-template-columns: 34px 1fr 1fr; } .rg, canvas, .hd span:nth-child(n+4) { display: none; } }
</style>
