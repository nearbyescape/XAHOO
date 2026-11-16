<script lang="ts">
  import { conn, status, model, markets, serverTime, tally } from '../lib/store';
  import { clock } from '../lib/format';
  import Needle from './Needle.svelte';
  $: ms = Object.values($markets);
  $: ages = ms.map(m => m.age).filter((a): a is number => a != null);
  $: age = ages.length ? Math.max(...ages) : null;
  // breadth: average 1h probability across the coins = a simple "risk on / risk off" reading
  $: ps = ms.filter(m => m.kind === 'coin' && m.forecast?.h?.['1h']?.show).map(m => m.forecast!.h['1h'].p);
  $: breadth = ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : 0.5;
  $: ups = ps.filter(p => p > 0.5).length;
  async function logout() { await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' }); location.replace('/login'); }
</script>
<header>
  <div class="brand"><span class="logo">XAHOO</span><span class="sub">DIRECTION PROBABILITY TERMINAL</span></div>
  <div class="risk" title="Average 1-hour probability across the eight coins">
    <Needle slow={breadth} fast={breadth} hasFast={false} />
    <div><div class="lbl">MARKET TILT · 1H</div><div class="val num" class:up={breadth > 0.505} class:down={breadth < 0.495}>{ups}/{ps.length || 8} coins lean up</div></div>
  </div>
  <div class="right">
    <span class="badge" class:live={$conn === 'live'} class:down={$conn === 'down'}>
      <i class="dot"></i>{$conn === 'live' ? ($status.feed || 'live') : $conn === 'down' ? 'reconnecting' : 'connecting'}
    </span>
    <span class="kv" title="Age of the oldest market's last update">DATA <b class="num">{age == null ? '—' : age < 1 ? `${Math.round(age * 1000)} ms` : `${age.toFixed(1)} s`}</b></span>
    <span class="kv" title="Time to compute all forecasts each minute">CALC <b class="num">{$status.compute_ms ?? '—'} ms</b></span>
    <span class="kv" title="Forecasts resolved since this page opened">SESSION <b class="num">{$tally.n ? `${(($tally.hit / $tally.n) * 100).toFixed(1)}% of ${$tally.n}` : '—'}</b></span>
    <span class="kv">MODEL <b>{$model.version}</b></span>
    <span class="clock num">{clock($serverTime)} <span class="dim">UTC</span> · {clock($serverTime, 'Asia/Kolkata')} <span class="dim">IST</span></span>
    <button on:click={logout} title="Log out">⏻</button>
  </div>
</header>
<style>
  header { display: flex; align-items: center; gap: 22px; padding: 6px 14px; border-bottom: 1px solid var(--line); background: color-mix(in srgb, var(--panel) 88%, transparent); position: sticky; top: 0; z-index: 10; backdrop-filter: blur(6px); flex-wrap: wrap; }
  .brand { display: flex; align-items: baseline; gap: 12px; }
  .logo { color: var(--amber); font-weight: 700; letter-spacing: 5px; font-size: 17px; }
  .sub { color: var(--dim); font-size: 9.5px; letter-spacing: 2.2px; }
  .risk { display: flex; align-items: center; gap: 8px; }
  .risk :global(.needle) { width: 64px; height: 34px; }
  .lbl { font-size: 9px; letter-spacing: 1.4px; color: var(--dim); }
  .val { font-size: 11px; }
  .right { margin-left: auto; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .badge { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line2); padding: 2px 8px; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; color: var(--dim); }
  .badge.live { color: var(--up); border-color: color-mix(in srgb, var(--up) 50%, transparent); }
  .badge.down { color: var(--down); border-color: var(--down); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .badge.live .dot { animation: beat 1.6s ease-in-out infinite; }
  @keyframes beat { 0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; } 50% { opacity: .5; box-shadow: 0 0 0 4px transparent; } }
  .kv { font-size: 9.5px; letter-spacing: 1.2px; color: var(--dim); }
  .kv b { color: var(--text); font-weight: 500; letter-spacing: 0; font-size: 11px; margin-left: 4px; }
  .clock { font-size: 11px; }
  @media (max-width: 900px) { .sub, .kv { display: none; } header { gap: 10px; } }
</style>
