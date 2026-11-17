<script lang="ts">
  // One market at a time: chosen in the top bar's coin picker; every panel on screen is about that market.
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { connect, checkAuth, markets, order, conn, connError, focus } from './lib/store';
  import TopBar from './components/TopBar.svelte';
  import FocusChart from './components/FocusChart.svelte';
  import Outlook from './components/Outlook.svelte';
  import Timeframes from './components/Timeframes.svelte';
  import TrackMini from './components/TrackMini.svelte';
  let restored = false;
  onMount(() => {
    checkAuth(); connect();
    try { const s = localStorage.getItem('tm.coin'); if (s) focus.set(s); } catch { /* private mode */ }
    restored = true;
  });
  $: if (restored) { try { localStorage.setItem('tm.coin', $focus); } catch { /* ignore */ } }
  $: if ($order.length && !$order.includes($focus)) focus.set($order[0]);      // a remembered market that no longer exists
</script>
<TopBar />
{#if !$order.length}
  <div class="wait"><span class="spin"></span>{$conn === 'down' ? 'Connection lost — reconnecting…' : 'Connecting to the live feed…'}{#if $connError}<em class="err">{$connError}</em>{/if}</div>
{:else if $markets[$focus]}
  {#key $focus}
    <main class="one" in:fade={{ duration: 300 }}>
      <div class="b"><FocusChart sym={$focus} /></div>
      <div class="c"><Outlook sym={$focus} /></div>
      <div class="d"><Timeframes m={$markets[$focus]} /></div>
      <div class="e"><TrackMini sym={$focus} /></div>
    </main>
  {/key}
{/if}
<style>
  .one { display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(0, 1fr) 450px; grid-template-rows: minmax(0, 1fr) 262px; gap: 12px;
    height: calc(100vh - 59px); padding: 12px 16px 14px; }
  .b, .c, .d, .e { min-width: 0; min-height: 0; display: flex; }
  .b { grid-column: 1 / 3; grid-row: 1; }
  .c { grid-column: 3; grid-row: 1 / 3; }
  .d { grid-column: 1; grid-row: 2; }
  .e { grid-column: 2; grid-row: 2; }
  .b > :global(*), .c > :global(*), .d > :global(*), .e > :global(*) { flex: 1; min-width: 0; }
  .wait { padding: 120px; text-align: center; color: var(--muted); display: flex; gap: 12px; justify-content: center; align-items: center; }
  .err { display: block; font-style: normal; font-size: 11px; color: var(--down); margin-left: 10px; }
  .spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--line2); border-top-color: var(--accent); animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 1500px) {
    .one { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-rows: 640px auto auto; height: auto; }
    .b { grid-column: 1 / 3; grid-row: 1; } .d { grid-column: 1 / 3; grid-row: 2; height: 262px; }
    .c { grid-column: 1; grid-row: 3; } .e { grid-column: 2; grid-row: 3; }
  }
  @media (max-width: 900px) {
    .one { grid-template-columns: 1fr; grid-template-rows: auto; padding: 10px; }
    .b, .c, .d, .e { grid-column: 1; grid-row: auto; }
    .b { height: 540px; } .e { height: 320px; }
  }
</style>
