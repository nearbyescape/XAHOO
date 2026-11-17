<script lang="ts">
  import CoinPicker from './CoinPicker.svelte';
  import { conn, connError, status, model, markets, order, serverTime, tally } from '../lib/store';
  import { clock } from '../lib/format';
  $: ms = $order.map(s => $markets[s]).filter(Boolean);
  $: ages = ms.map(m => m.age).filter((a): a is number => a != null);
  $: age = ages.length ? Math.max(...ages) : null;
  async function logout() { await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' }); location.replace('/login'); }
</script>
<header>
  <div class="brand">
    <img class="emb" src="/icons/icon-192.png" alt="">
    <div><div class="logo">TREND MACHINE</div><div class="sub">Futures direction terminal · Binance USDⓈ-M perpetuals</div></div>
  </div>
  <CoinPicker />
  <div class="right">
    <span class="live" class:ok={$conn === 'live'} class:poll={$conn === 'polling'} class:bad={$conn === 'down'}
      title={$conn === 'polling' ? 'WebSocket blocked (check the nginx Upgrade headers); updating over HTTPS every 1.5 s' : $connError}><i></i>{$conn === 'live' ? ($status.feed || 'live') : $conn === 'polling' ? `${$status.feed || 'live'} · https` : $conn === 'down' ? 'reconnecting' : 'connecting'}</span>
    <span class="kv" title="Age of the oldest market's last update"><em>Data</em><b class="num">{age == null ? '—' : age < 1 ? `${Math.round(age * 1000)}ms` : `${age.toFixed(1)}s`}</b></span>
    <span class="kv" title="Time to compute all forecasts each minute"><em>Calc</em><b class="num">{$status.compute_ms ?? '—'}ms</b></span>
    <span class="kv" title="Forecasts resolved since this page opened: share whose more-likely direction came true"><em>Session</em><b class="num">{$tally.n ? `${(($tally.hit / $tally.n) * 100).toFixed(1)}% · ${$tally.n}` : '—'}</b></span>
    <span class="kv"><em>Model</em><b class="num">{$model.version}</b></span>
    <span class="clock num">{clock($serverTime)}<em>UTC</em>{clock($serverTime, 'Asia/Kolkata')}<em>IST</em></span>
    <button class="icon" on:click={logout} title="Log out" aria-label="Log out"><svg viewBox="0 0 24 24"><path d="M12 3v8M6.3 6.8a8 8 0 1 0 11.4 0" /></svg></button>
  </div>
</header>
<style>
  header { display: flex; align-items: center; gap: 26px; padding: 10px 20px; position: sticky; top: 0; z-index: 20; flex-wrap: wrap;
    background: rgba(7, 10, 19, .72); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border-bottom: 1px solid var(--line); }
  .brand { display: flex; align-items: center; gap: 11px; }
  .emb { width: 38px; height: 38px; border-radius: 50%; box-shadow: 0 4px 16px rgba(56,198,244,.3); }
  .logo { font: 800 16px var(--sans); letter-spacing: 2.5px; background: var(--brand); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .sub { font-size: 10.5px; color: var(--faint); letter-spacing: .4px; margin-top: -1px; }
  .right { margin-left: auto; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .live { display: inline-flex; align-items: center; gap: 7px; font: 600 10.5px var(--sans); letter-spacing: 1px; text-transform: uppercase; color: var(--muted);
    padding: 4px 10px; border-radius: 99px; border: 1px solid var(--line2); }
  .live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .live.ok { color: var(--up); border-color: rgba(var(--up-rgb), .35); background: rgba(var(--up-rgb), .06); }
  .live.ok i { animation: beat 1.8s ease-in-out infinite; }
  .live.poll { color: var(--res); border-color: rgba(255,181,71,.4); background: rgba(255,181,71,.06); }
  .live.bad { color: var(--down); border-color: rgba(var(--down-rgb), .4); }
  @keyframes beat { 0%, 100% { box-shadow: 0 0 0 0 rgba(var(--up-rgb), .6); } 60% { box-shadow: 0 0 0 6px rgba(var(--up-rgb), 0); } }
  .kv { display: flex; flex-direction: column; line-height: 1.2; }
  .kv em, .clock em { font: 600 9px var(--sans); font-style: normal; letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); }
  .kv b { font-size: 12px; font-weight: 500; color: var(--text); }
  .clock { font-size: 13px; display: flex; align-items: baseline; gap: 4px; }
  .clock em { margin-right: 8px; }
  .icon { padding: 5px; display: grid; place-items: center; }
  .icon svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
  @media (max-width: 1100px) { .kv, .sub { display: none; } }
  @media (max-width: 700px) { header { gap: 12px; padding: 8px 12px; } .clock em:last-of-type { display: none; } }
</style>
