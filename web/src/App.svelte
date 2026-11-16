<script lang="ts">
  import { onMount } from 'svelte';
  import { flip } from 'svelte/animate';
  import { connect, checkAuth, markets, order, horizons, selected, conn, model, sortMode } from './lib/store';
  import TopBar from './components/TopBar.svelte';
  import Card from './components/Card.svelte';
  import Detail from './components/Detail.svelte';
  import TrackRecord from './components/TrackRecord.svelte';
  onMount(() => { checkAuth(); connect(); });
  // "strongest first": by how far the shown 15m–4h probabilities lean from 50%, re-sorted once a minute
  let sorted: string[] = [];
  let lastSort = 0;
  $: {
    const t = $markets[$order[0]]?.forecast?.ts || 0;
    if ($sortMode === 'fixed') sorted = $order;
    else if (t !== lastSort || sorted.length !== $order.length || sorted === $order) {
      lastSort = t;
      const strength = (s: string) => {
        const f = $markets[s]?.forecast?.h || {};
        const v = ['15m', '1h', '4h'].map(h => f[h]).filter(x => x && x.show).map(x => Math.abs(x.p - 0.5));
        return v.length ? v.reduce((a, b) => a + b, 0) / v.length : -1;
      };
      sorted = [...$order].sort((a, b) => strength(b) - strength(a));
    }
  }
  function key(e: KeyboardEvent) {
    if (e.key === 'Escape') selected.set(null);
    if (!$selected) return;
    const i = sorted.indexOf($selected);
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); selected.set(sorted[Math.min(sorted.length - 1, i + 1)]); }
    if ((e.key === 'ArrowUp' || e.key === 'ArrowLeft') && i > 0) { e.preventDefault(); selected.set(sorted[i - 1]); }
  }
</script>
<svelte:window on:keydown={key} />
<TopBar />
<main>
  <section class="grid">
    {#each sorted as sym (sym)}
      <div class="slot" animate:flip={{ duration: 600 }}><Card m={$markets[sym]} hs={$horizons} /></div>
    {:else}
      <div class="wait panel"><span class="spin"></span>{$conn === 'down' ? 'Connection lost — reconnecting…' : 'Connecting to the live feed…'}</div>
    {/each}
  </section>
  <div class="legend">
    <span><b class="up">▲ 56%</b> chance the Binance mark price is higher at the end of the window</span>
    <span><b>±</b> expected move (68% range)</span>
    <span><b class="res">R</b> / <b class="sup">S</b> nearest resistance / support · reach = measured chance price trades there</span>
    <span>Dial: thick needle 15m–4h, dashed needle 1–5 min</span>
    <span class="faint">Probabilities are measured frequencies from 2024–26 tests (model {$model.version}), not advice.</span>
  </div>
  <TrackRecord />
</main>
{#if $selected && $markets[$selected]}
  {#key $selected}<Detail sym={$selected} />{/key}
{/if}
<style>
  main { display: flex; flex-direction: column; gap: 14px; padding: 16px 20px 28px; max-width: 2400px; margin: 0 auto; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(340px, 100%), 1fr)); gap: 14px; }
  .slot { min-width: 0; }
  .wait { grid-column: 1 / -1; padding: 80px; text-align: center; color: var(--muted); display: flex; gap: 12px; justify-content: center; align-items: center; }
  .spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--line2); border-top-color: var(--accent); animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 11px; color: var(--muted); padding: 0 4px; }
  .legend b { font-weight: 700; font-family: var(--mono); }
  @media (max-width: 720px) { main { padding: 12px; } .grid { grid-template-columns: 1fr; } }
</style>
