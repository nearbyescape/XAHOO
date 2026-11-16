<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { flip } from 'svelte/animate';
  import { fade } from 'svelte/transition';
  import { connect, checkAuth, markets, order, horizons, conn, model, sortMode, focus, view, cycle } from './lib/store';
  import TopBar from './components/TopBar.svelte';
  import Card from './components/Card.svelte';
  import Rail from './components/Rail.svelte';
  import FocusChart from './components/FocusChart.svelte';
  import Outlook from './components/Outlook.svelte';
  import Matrix from './components/Matrix.svelte';
  import TrackMini from './components/TrackMini.svelte';
  import TrackRecord from './components/TrackRecord.svelte';
  const CYCLE_S = 20;
  let cycleT = 0, timer: ReturnType<typeof setInterval>;
  onMount(() => {
    checkAuth(); connect();
    try { const v = localStorage.getItem('xahoo.view'); if (v === 'grid' || v === 'focus') view.set(v); } catch { /* private mode */ }
    timer = setInterval(() => {
      if (!$cycle || $view !== 'focus' || !$order.length) { cycleT = 0; return; }
      cycleT += 1;
      if (cycleT >= CYCLE_S) { cycleT = 0; focus.set($order[($order.indexOf($focus) + 1) % $order.length]); }
    }, 1000);
  });
  onDestroy(() => clearInterval(timer));
  $: try { localStorage.setItem('xahoo.view', $view); } catch { /* ignore */ }
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
    if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
    const i = $order.indexOf($focus);
    if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); focus.set($order[Math.min($order.length - 1, i + 1)]); cycleT = 0; }
    if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); focus.set($order[Math.max(0, i - 1)]); cycleT = 0; }
    if (e.key === 'g') view.set($view === 'grid' ? 'focus' : 'grid');
  }
</script>
<svelte:window on:keydown={key} />
<TopBar />
{#if !$order.length}
  <div class="wait"><span class="spin"></span>{$conn === 'down' ? 'Connection lost — reconnecting…' : 'Connecting to the live feed…'}</div>
{:else if $view === 'focus' && $markets[$focus]}
  <main class="focus" in:fade={{ duration: 250 }}>
    <div class="a"><Rail cycleLeft={cycleT / CYCLE_S} /></div>
    <div class="b">{#key $focus}<div class="fill" in:fade={{ duration: 300 }}><FocusChart sym={$focus} /></div>{/key}</div>
    <div class="c">{#key $focus}<div class="fill" in:fade={{ duration: 300 }}><Outlook sym={$focus} /></div>{/key}</div>
    <div class="d"><TrackMini /></div>
    <div class="e"><Matrix /></div>
  </main>
{:else}
  <main class="gridv" in:fade={{ duration: 250 }}>
    <section class="grid">
      {#each sorted as sym (sym)}
        <div class="slot" animate:flip={{ duration: 600 }}><Card m={$markets[sym]} hs={$horizons} /></div>
      {/each}
    </section>
    <div class="legend">
      <span><b class="up">▲ 56%</b> chance the Binance mark price is higher at the end of the window</span>
      <span><b>±</b> typical move (68% range)</span>
      <span><b class="res">R</b> / <b class="sup">S</b> nearest resistance / support · reach = measured chance price trades there</span>
      <span class="faint">Probabilities are measured frequencies from 2024–26 tests (model {$model.version}), not advice.</span>
    </div>
    <TrackRecord />
  </main>
{/if}
<style>
  .focus { display: grid; grid-template-columns: 290px minmax(0, 1fr) 450px; grid-template-rows: minmax(0, 1fr) 272px; gap: 12px;
    height: calc(100vh - 59px); padding: 12px 16px 14px; }
  .a, .b, .c, .d, .e { min-width: 0; }
  .a { grid-column: 1; grid-row: 1; min-height: 0; display: flex; }
  .b { grid-column: 2; grid-row: 1; min-height: 0; display: flex; }
  .c { grid-column: 3; grid-row: 1 / 3; min-height: 0; display: flex; }
  .d { grid-column: 1; grid-row: 2; min-height: 0; display: flex; }
  .e { grid-column: 2; grid-row: 2; min-height: 0; display: flex; }
  .a > :global(*), .b > :global(*), .c > :global(*), .d > :global(*), .e > :global(*), .fill > :global(*) { flex: 1; min-width: 0; }
  .fill { display: flex; flex: 1; min-width: 0; min-height: 0; }
  .gridv { display: flex; flex-direction: column; gap: 14px; padding: 16px 20px 28px; max-width: 2400px; margin: 0 auto; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(340px, 100%), 1fr)); gap: 14px; }
  .slot { min-width: 0; }
  .wait { padding: 120px; text-align: center; color: var(--muted); display: flex; gap: 12px; justify-content: center; align-items: center; }
  .spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--line2); border-top-color: var(--accent); animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 11px; color: var(--muted); padding: 0 4px; }
  .legend b { font-weight: 700; font-family: var(--mono); }
  @media (max-width: 1500px) {
    .focus { grid-template-columns: 250px minmax(0, 1fr); grid-template-rows: 620px auto auto; height: auto; }
    .c { grid-column: 1 / 3; grid-row: 3; } .d { grid-column: 1; grid-row: 2; height: 300px; } .e { grid-column: 2; grid-row: 2; }
  }
  @media (max-width: 900px) {
    .focus { grid-template-columns: 1fr; grid-template-rows: auto; padding: 10px; }
    .a, .b, .c, .d, .e { grid-column: 1; grid-row: auto; }
    .a { max-height: 340px; } .b { height: 520px; } .d { height: 300px; }
  }
  @media (max-width: 720px) { .gridv { padding: 12px; } .grid { grid-template-columns: 1fr; } }
</style>
