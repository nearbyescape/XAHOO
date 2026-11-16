<script lang="ts">
  import { conn, status, model, markets, order, serverTime, tally, sortMode } from '../lib/store';
  import { clock, probColor } from '../lib/format';
  $: ms = $order.map(s => $markets[s]).filter(Boolean);
  $: ages = ms.map(m => m.age).filter((a): a is number => a != null);
  $: age = ages.length ? Math.max(...ages) : null;
  // tilt: each coin's 1h probability; the average reads as "risk on / risk off"
  $: coins = ms.filter(m => m.kind === 'coin');
  $: ps = coins.filter(m => m.forecast?.h?.['1h']?.show).map(m => m.forecast!.h['1h'].p);
  $: breadth = ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : 0.5;
  $: ups = ps.filter(p => p > 0.5).length;
  async function logout() { await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' }); location.replace('/login'); }
</script>
<header>
  <div class="brand">
    <span class="mark"><svg viewBox="0 0 24 24"><path d="M4 18 L10 11 L14 14 L20 6" /><circle cx="20" cy="6" r="2" /></svg></span>
    <div><div class="logo">XAHOO</div><div class="sub">Direction probability terminal</div></div>
  </div>
  <div class="tilt" title="1-hour probability for each coin; the average is the market tilt">
    <div class="label">Market tilt · 1h</div>
    <div class="chips">
      {#each coins as m (m.sym)}
        {@const f = m.forecast?.h?.['1h']}
        <span class="c" style="background:{f?.show ? probColor(f.p, .9) : 'var(--line2)'}; height:{f?.show ? 8 + Math.min(14, Math.abs(f.p - 0.5) * 200) : 6}px" title="{m.short} {f?.show ? (f.p * 100).toFixed(1) + '% up' : 'no edge'}"></span>
      {/each}
      <span class="tv num" style="color:{probColor(breadth)}">{ups}/{ps.length || coins.length} up · {(breadth * 100).toFixed(1)}%</span>
    </div>
  </div>
  <div class="seg" role="group" aria-label="Card order">
    <button class:on={$sortMode === 'fixed'} on:click={() => sortMode.set('fixed')}>Fixed</button>
    <button class:on={$sortMode === 'strongest'} on:click={() => sortMode.set('strongest')}>Strongest first</button>
  </div>
  <div class="right">
    <span class="live" class:ok={$conn === 'live'} class:bad={$conn === 'down'}><i></i>{$conn === 'live' ? ($status.feed || 'live') : $conn === 'down' ? 'reconnecting' : 'connecting'}</span>
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
  .mark { width: 34px; height: 34px; border-radius: 10px; background: var(--brand); display: grid; place-items: center; box-shadow: 0 6px 20px rgba(139,124,255,.35); }
  .mark svg { width: 20px; height: 20px; fill: none; stroke: #0a0d18; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
  .mark circle { fill: #0a0d18; stroke: none; }
  .logo { font: 800 17px var(--sans); letter-spacing: 4px; background: var(--brand); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .sub { font-size: 10.5px; color: var(--faint); letter-spacing: .4px; margin-top: -1px; }
  .tilt { display: flex; flex-direction: column; gap: 3px; }
  .chips { display: flex; align-items: flex-end; gap: 3px; height: 22px; }
  .c { width: 7px; border-radius: 2px; transition: height .6s ease, background .6s; }
  .tv { margin-left: 8px; font-size: 12px; font-weight: 600; align-self: center; }
  .seg { display: inline-flex; gap: 0; }
  .seg button { border-radius: 0; padding: 5px 10px; font-size: 11px; }
  .seg button:first-child { border-radius: 8px 0 0 8px; } .seg button:last-child { border-radius: 0 8px 8px 0; border-left: 0; }
  .right { margin-left: auto; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .live { display: inline-flex; align-items: center; gap: 7px; font: 600 10.5px var(--sans); letter-spacing: 1px; text-transform: uppercase; color: var(--muted);
    padding: 4px 10px; border-radius: 99px; border: 1px solid var(--line2); }
  .live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .live.ok { color: var(--up); border-color: rgba(var(--up-rgb), .35); background: rgba(var(--up-rgb), .06); }
  .live.ok i { animation: beat 1.8s ease-in-out infinite; }
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
  @media (max-width: 700px) { header { gap: 12px; padding: 8px 12px; } .seg, .clock em:last-of-type { display: none; } .tilt .label { display: none; } }
</style>
