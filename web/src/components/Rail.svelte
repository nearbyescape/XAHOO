<script lang="ts">
  import Arrow from './Arrow.svelte';
  import CoinLogo from './CoinLogo.svelte';
  // Left market list: price, 24h change and the 15m–4h lean; the focused market is highlighted.
  import { markets, order, focus, cycle } from '../lib/store';
  import { px, pct, probColor, lean, conviction } from '../lib/format';
  import Roll from './Roll.svelte';
  export let cycleLeft = 0;              // 0..1 progress of the auto-cycle timer
  const blend = (f: Record<string, any>) => {
    const v = ['15m', '1h', '4h'].map(k => f?.[k]).filter(x => x && x.show).map(x => x.p);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
</script>
<nav class="rail panel">
  <div class="ph">Markets <span class="r">bias 15m–4h</span></div>
  {#each $order as sym (sym)}
    {@const m = $markets[sym]}{@const b = blend(m.forecast?.h || {})}
    {@const chg = m.price != null && m.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null}
    <button class="it" class:on={$focus === sym} on:click={() => focus.set(sym)} style="--c:{b != null ? probColor(b) : 'var(--faint)'}">
      <span class="badge"><CoinLogo {sym} short={m.short} size={34} glow={$focus === sym} /></span>
      <span class="id"><b>{m.short}</b><em>{m.name}</em></span>
      <span class="px"><span class="num p"><Roll value={m.price} format={v => px(v, m.digits)} /></span>
        <span class="num ch" class:up={chg != null && chg >= 0} class:down={chg != null && chg < 0}>{pct(chg)}</span></span>
      <span class="ln">
        {#if b != null}
          <span class="arr num"><Arrow p={b} size={17} /> <i class="ls">{conviction(b) === 0 ? '–' : b >= 0.5 ? 'L' : 'S'}</i>{((b >= 0.5 ? b : 1 - b) * 100).toFixed(1)}</span>
          <span class="bar"><i style="width:{Math.abs(lean(b)) * 50}%; {b >= 0.5 ? 'left:50%' : 'right:50%'}"></i></span>
        {:else}<span class="ne">no edge</span>{/if}
      </span>
      {#if $focus === sym && $cycle}<i class="cyc" style="width:{cycleLeft * 100}%"></i>{/if}
    </button>
  {/each}
</nav>
<style>
  .rail { display: flex; flex-direction: column; min-height: 0; overflow-y: auto; }
  .it { position: relative; display: grid; grid-template-columns: 34px 1fr auto; grid-template-rows: auto auto; gap: 2px 10px; align-items: center;
    text-align: left; border: 0; border-radius: 0; border-top: 1px solid var(--line); padding: 9px 14px; background: transparent; flex: 1; min-height: 62px; }
  .it:hover { background: rgba(148,163,214,.05); }
  .it.on { background: linear-gradient(90deg, rgba(139,124,255,.16), rgba(139,124,255,.02)); box-shadow: inset 3px 0 var(--accent); }
  .badge { grid-row: 1 / 3; display: grid; place-items: center; }
  .id { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
  .id b { font: 700 14px var(--sans); color: var(--text); } .id em { font-style: normal; font-size: 11px; color: var(--faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .px { grid-row: 1; grid-column: 3; text-align: right; display: flex; gap: 8px; align-items: baseline; }
  .p { font-size: 13.5px; color: var(--text); font-weight: 600; } .ch { font-size: 10.5px; color: var(--muted); }
  .ln { grid-column: 2 / 4; display: grid; grid-template-columns: 68px 1fr; gap: 8px; align-items: center; }
  .ls { font: 800 9.5px var(--sans); font-style: normal; letter-spacing: .5px; }
  .arr { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700; color: var(--c); transition: color .6s; }
  .bar { position: relative; height: 5px; border-radius: 3px; background: rgba(148,163,214,.09); }
  .bar::after { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line3); }
  .bar i { position: absolute; top: 0; bottom: 0; border-radius: 3px; background: var(--c); box-shadow: 0 0 8px var(--c); transition: width .7s ease, background .6s; }
  .ne { font-size: 10.5px; color: var(--faint); }
  .cyc { position: absolute; left: 0; bottom: 0; height: 2px; background: var(--brand); transition: width 1s linear; }
</style>
