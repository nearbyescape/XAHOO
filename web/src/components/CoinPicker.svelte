<script lang="ts">
  // Coin selector: the one market the whole screen is about. The list shows each market's price, 24h change and
  // overall direction so a choice can be made at a glance. Keyboard: ↑ ↓ to move, Enter to pick, Esc to close.
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { markets, order, focus } from '../lib/store';
  import { px, pct, probColor, overall } from '../lib/format';
  import CoinLogo from './CoinLogo.svelte';
  import Arrow from './Arrow.svelte';
  let open = false, hi = 0, root: HTMLDivElement;
  $: cur = $markets[$focus];
  function toggle() { open = !open; hi = Math.max(0, $order.indexOf($focus)); }
  function pick(sym: string) { focus.set(sym); open = false; }
  function key(e: KeyboardEvent) {
    if (!open) { if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } return; }
    if (e.key === 'Escape') { open = false; }
    else if (e.key === 'ArrowDown') { e.preventDefault(); hi = (hi + 1) % $order.length; }
    else if (e.key === 'ArrowUp') { e.preventDefault(); hi = (hi - 1 + $order.length) % $order.length; }
    else if (e.key === 'Enter') { e.preventDefault(); pick($order[hi]); }
  }
  function outside(e: MouseEvent) { if (open && root && !root.contains(e.target as Node)) open = false; }
  const chg = (m: any) => (m?.price != null && m?.dayAgo ? (m.price / m.dayAgo - 1) * 100 : null);
</script>
<svelte:window on:mousedown={outside} />
<div class="pk" bind:this={root}>
  {#if cur}
    <button class="cur" class:open on:click={toggle} on:keydown={key} aria-haspopup="listbox" aria-expanded={open} title="Choose a market">
      {#key $focus}<span class="lg" in:fly={{ y: 6, duration: 300, easing: cubicOut }}><CoinLogo sym={cur.sym} short={cur.short} size={30} /></span>{/key}
      <span class="nm"><b>{cur.short}</b><em>{cur.name} · perpetual</em></span>
      <svg class="chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" /></svg>
    </button>
  {/if}
  {#if open}
    <div class="menu panel" role="listbox" transition:fly={{ y: -8, duration: 220, easing: cubicOut }}>
      <div class="mh"><span>Market</span><span class="r">Price · 24h</span><span class="r">Overall</span></div>
      {#each $order as sym, i (sym)}
        {@const m = $markets[sym]}{@const o = overall(m?.forecast)}{@const c = chg(m)}
        <button class="row" class:sel={sym === $focus} class:hi={i === hi} role="option" aria-selected={sym === $focus}
          on:mouseenter={() => (hi = i)} on:click={() => pick(sym)}>
          <CoinLogo {sym} short={m.short} size={26} glow={sym === $focus} />
          <span class="id"><b>{m.short}</b><em>{m.name}</em></span>
          <span class="px num">{px(m.price, m.digits)}<i class:up={c != null && c >= 0} class:down={c != null && c < 0}>{pct(c)}</i></span>
          <span class="ov num" style="color:{o ? probColor(o.p) : 'var(--faint)'}">
            {#if o}<Arrow p={o.p} lab={o.lab} size={16} glow={false} />{o.lab === 0 ? `${(o.p * 100).toFixed(1)}% up` : `${((o.p >= 0.5 ? o.p : 1 - o.p) * 100).toFixed(1)}%`}{#if !o.head}<small>{o.tf}</small>{/if}{:else}no edge{/if}
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>
<style>
  .pk { position: relative; }
  .cur { display: flex; align-items: center; gap: 10px; padding: 5px 12px 5px 6px; border-radius: 14px; min-width: 230px;
    background: linear-gradient(135deg, rgba(139,124,255,.12), rgba(56,198,244,.06)); border: 1px solid var(--line2); transition: border-color .2s, box-shadow .2s; }
  .cur:hover, .cur.open { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(139,124,255,.15); }
  .lg { display: inline-flex; }
  .nm { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.15; flex: 1; }
  .nm b { font: 800 15px var(--sans); letter-spacing: .5px; color: var(--text); }
  .nm em { font-style: normal; font-size: 10.5px; color: var(--faint); }
  .chev { width: 16px; height: 16px; fill: none; stroke: var(--muted); stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; transition: transform .25s; }
  .open .chev { transform: rotate(180deg); }
  .menu { position: absolute; top: calc(100% + 8px); left: 0; z-index: 50; width: 430px; padding: 6px; display: flex; flex-direction: column;
    background: linear-gradient(180deg, #11162a, #0b0f1e); box-shadow: 0 24px 60px rgba(0,0,0,.65), 0 0 0 1px var(--line2); }
  .mh { display: grid; grid-template-columns: 1fr 120px 104px; padding: 4px 10px 6px; font: 600 9.5px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); }
  .mh .r { text-align: right; }
  .row { display: grid; grid-template-columns: 26px 1fr 120px 104px; align-items: center; gap: 10px; padding: 7px 10px; border: 0; border-radius: 10px;
    background: transparent; text-align: left; transition: background .15s; }
  .row.hi { background: rgba(148,163,214,.08); }
  .row.sel { background: linear-gradient(90deg, rgba(139,124,255,.18), rgba(139,124,255,.03)); box-shadow: inset 3px 0 var(--accent); }
  .id { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
  .id b { font: 700 13px var(--sans); color: var(--text); } .id em { font-style: normal; font-size: 11px; color: var(--faint); }
  .px { display: flex; flex-direction: column; align-items: flex-end; font-size: 12.5px; color: var(--text); line-height: 1.2; }
  .px i { font-style: normal; font-size: 10.5px; color: var(--muted); }
  .px i.up { color: var(--up); } .px i.down { color: var(--down); }
  .ov { display: inline-flex; align-items: center; justify-content: flex-end; gap: 5px; font-size: 12.5px; font-weight: 700; }
  .ov small { font: 600 9px var(--sans); color: var(--faint); }
  @media (max-width: 700px) { .menu { width: calc(100vw - 24px); } .cur { min-width: 0; } .nm em { display: none; } }
</style>
