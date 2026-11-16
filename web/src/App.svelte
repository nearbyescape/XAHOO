<script lang="ts">
  import { onMount } from 'svelte';
  import { connect, checkAuth, markets, order, horizons, selected, conn, model } from './lib/store';
  import TopBar from './components/TopBar.svelte';
  import Row from './components/Row.svelte';
  import Detail from './components/Detail.svelte';
  import Scoreboard from './components/Scoreboard.svelte';
  onMount(() => { checkAuth(); connect(); });
  $: cols = `150px 128px 176px 112px repeat(${$horizons.length || 6}, minmax(92px, 1fr))`;
  function key(e: KeyboardEvent) {
    if (e.key === 'Escape') selected.set(null);
    const i = $order.indexOf($selected || '');
    if (e.key === 'ArrowDown' && $order.length) { e.preventDefault(); selected.set($order[Math.min($order.length - 1, i + 1)]); }
    if (e.key === 'ArrowUp' && i > 0) { e.preventDefault(); selected.set($order[i - 1]); }
  }
</script>
<svelte:window on:keydown={key} />
<TopBar />
<main>
  <div class="left">
    <section class="panel board" style="--cols:{cols}">
      <div class="head">
        <span>MARKET</span><span class="r">PRICE · 24H</span><span>FLOW · 60 S</span><span class="c">DIRECTION</span>
        {#each $horizons as h}<span class="c hz">{h}</span>{/each}
      </div>
      {#each $order as sym (sym)}
        <Row m={$markets[sym]} hs={$horizons} />
      {:else}
        <div class="wait">{$conn === 'down' ? 'Connection lost — reconnecting…' : 'Connecting to the live feed…'}</div>
      {/each}
      <div class="foot dim">
        <span><b class="up">▲ 56%</b> = 56% chance the Binance mark price is higher at the end of the window · <b>±</b> = expected move (68% band) · bar under a cell = confidence · thin needle = 1–5 minute push, thick needle = 15 m–4 h</span>
        <span>Probabilities are measured frequencies from history (model {$model.version}), not advice.</span>
      </div>
    </section>
    {#if $selected && $markets[$selected]}
      {#key $selected}<Detail sym={$selected} />{/key}
    {/if}
  </div>
  <aside><Scoreboard /></aside>
</main>
<style>
  main { display: grid; grid-template-columns: minmax(0, 1fr) 372px; gap: 10px; padding: 10px; align-items: start; }
  .left { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  aside { position: sticky; top: 56px; height: calc(100vh - 66px); min-height: 400px; }
  .board { overflow-x: auto; }
  .head { display: grid; grid-template-columns: var(--cols); padding: 7px 0; border-bottom: 1px solid var(--line2); font-size: 9.5px; letter-spacing: 1.6px; color: var(--dim); min-width: max-content; }
  .head span { padding: 0 12px; } .head .r { text-align: right; } .head .c { text-align: center; }
  .head .hz { color: var(--amber); text-align: left; padding-left: 11px; font-weight: 600; font-size: 11px; }
  .board :global(.row) { min-width: max-content; }
  .wait { padding: 60px; text-align: center; color: var(--dim); }
  .foot { display: flex; justify-content: space-between; gap: 20px; padding: 8px 12px; font-size: 10px; line-height: 1.5; flex-wrap: wrap; }
  .foot b { font-weight: 600; }
  @media (max-width: 1280px) { main { grid-template-columns: 1fr; } aside { position: static; height: 560px; } }
</style>
