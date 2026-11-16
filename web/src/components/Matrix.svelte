<script lang="ts">
  // Every market at a glance: probability per horizon, position between support and resistance,
  // order-book tilt and big-trade flow. Click a row to focus it.
  import { markets, order, horizons, focus } from '../lib/store';
  import { probColor, probBg, BADGE } from '../lib/format';
  const pos = (m: any) => {
    const R = m.forecast?.levels?.resistance?.[0]?.price, S = m.forecast?.levels?.support?.[0]?.price;
    if (!R || !S || !m.price) return null;
    return Math.max(0, Math.min(1, Math.log(m.price / S) / Math.log(R / S)));
  };
</script>
<section class="mx panel">
  <div class="ph">All markets <span class="r">click a row to focus</span></div>
  <div class="tbl">
    <div class="hd"><span>Market</span>{#each $horizons as h}<span class="c">{h}</span>{/each}<span class="c">S ⟷ R</span><span class="c">Book</span><span class="c">Big trades 15m</span></div>
    {#each $order as sym (sym)}
      {@const m = $markets[sym]}{@const bd = BADGE[sym] || ['#8b7cff', '#38c6f4']}{@const ps = pos(m)}
      {@const bi = m.book?.['imb_0.25']}{@const tot = (m.big15?.[0] || 0) + (m.big15?.[1] || 0)}
      <button class="row" class:on={$focus === sym} on:click={() => focus.set(sym)}>
        <span class="mk"><i style="background:linear-gradient(135deg, {bd[0]}, {bd[1]})"></i>{m.short}</span>
        {#each $horizons as h}
          {@const f = m.forecast?.h?.[h]}
          {#key m.changed[h]}
            <span class="cell num" class:off={!f?.show} class:fl={!!m.changed[h]} style={f?.show ? `background:${probBg(f.p, 0.32)}; color:${probColor(f.p)}` : ''}>
              {#if f?.show}{f.p >= 0.5 ? '▲' : '▼'}{((f.p >= 0.5 ? f.p : 1 - f.p) * 100).toFixed(0)}{:else}·{/if}
            </span>
          {/key}
        {/each}
        <span class="srp">{#if ps != null}<span class="trk"><i style="left:{ps * 100}%"></i></span>{:else}<span class="faint">—</span>{/if}</span>
        <span class="bk">{#if bi != null}<span class="ib"><i style="width:{bi * 100}%"></i></span>{:else}<span class="faint">—</span>{/if}</span>
        <span class="bg">{#if tot > 0}<span class="ib"><i style="width:{(m.big15[0] / tot) * 100}%"></i></span>{:else}<span class="faint">none</span>{/if}</span>
      </button>
    {/each}
  </div>
</section>
<style>
  .mx { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .tbl { padding: 0 12px 10px; overflow: auto; }
  .hd, .row { display: grid; grid-template-columns: 74px repeat(6, minmax(44px, 1fr)) 1.3fr 1fr 1.1fr; gap: 4px; align-items: center; }
  .hd { font: 600 9.5px var(--sans); letter-spacing: 1px; text-transform: uppercase; color: var(--faint); padding: 0 6px 4px; }
  .hd .c { text-align: center; }
  .row { border: 0; border-radius: 7px; padding: 2px 6px; background: transparent; width: 100%; height: 24px; }
  .row:hover { background: rgba(148,163,214,.05); }
  .row.on { background: rgba(139,124,255,.13); box-shadow: inset 0 0 0 1px rgba(139,124,255,.4); }
  .mk { display: flex; align-items: center; gap: 6px; font: 700 11.5px var(--sans); color: var(--text); text-align: left; }
  .mk i { width: 8px; height: 8px; border-radius: 3px; }
  .cell { height: 19px; border-radius: 5px; font-size: 11px; font-weight: 700; display: grid; place-items: center; transition: background .8s ease, color .6s; }
  .cell.off { color: var(--faint); background: repeating-linear-gradient(135deg, rgba(148,163,214,.05) 0 3px, transparent 3px 6px); }
  .cell.fl { animation: fl 1.4s ease-out; }
  @keyframes fl { from { box-shadow: 0 0 0 1px var(--accent), 0 0 14px rgba(139,124,255,.6); } to { box-shadow: none; } }
  .srp, .bk, .bg { padding: 0 6px; }
  .trk { position: relative; display: block; height: 5px; border-radius: 3px; background: linear-gradient(90deg, var(--sup), rgba(148,163,214,.18) 40%, rgba(148,163,214,.18) 60%, var(--res)); }
  .trk i { position: absolute; top: 50%; width: 9px; height: 9px; margin-left: -4.5px; transform: translateY(-50%); border-radius: 50%; background: var(--text); box-shadow: 0 0 8px rgba(255,255,255,.5); transition: left .7s ease; }
  .ib { position: relative; display: block; height: 6px; border-radius: 3px; background: rgba(var(--down-rgb), .6); overflow: hidden; }
  .ib i { position: absolute; left: 0; top: 0; bottom: 0; background: var(--up); transition: width .7s ease; }
  .ib::after { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: rgba(255,255,255,.6); }
  .faint { font-size: 10px; }
</style>
