<script lang="ts">
  import Arrow from './Arrow.svelte';
  import { fly, fade } from 'svelte/transition';
  import { markets, fh, skill, levelsInfo, bigUsd, now, serverTime } from '../lib/store';
  import type { Market, Level } from '../lib/types';
  import { px, pct, usd, probColor, ago, biasWord, conviction, dirOf } from '../lib/format';
  import Gauge from './Gauge.svelte';
  export let sym: string;
  $: m = $markets[sym] as Market;
  $: f = m?.forecast?.h?.[$fh];
  $: sk = $skill[sym]?.[$fh];
  $: lv = m?.forecast?.levels;
  $: reasons = f?.reasons || [];
  $: maxW = Math.max(0.05, ...reasons.map(r => Math.abs(r.w)));
  $: bk = m?.book;
  $: big = (m?.big || []).slice(-7).reverse();
  $: b15 = m?.big15 || [0, 0];
  $: zones = m?.forecast?.profile?.zones;
  $: hold = $levelsInfo?.hold;
  const dist = (p: number) => (m?.price ? (p / m.price - 1) * 100 : 0);
  const reach = (x: Level, h: string) => (x.reach?.[h] != null ? `${Math.round(x.reach[h] * 100)}%` : '—');
  $: rh = ['15m', '1h', '4h', '1d'].includes($fh) ? $fh : '1h';
  const fmtLeft = (s: number) => (s <= 0 ? 'now' : s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`);
  const pctOf = (a: number, b: number) => (a + b > 0 ? a / (a + b) : 0.5);
</script>
<aside class="ol panel">
  <!-- outlook -->
  <div class="blk head">
    <Gauge slow={f?.show ? f.p : 0.5} fast={f?.show ? f.p : 0.5} hasFast={false} size={132} />
    <div class="hl">
      {#if f?.show}
        <div class="pbig num" style="color:{probColor(f.p)}"><Arrow p={f.p} lab={f.lab} size={40} />{((f.p >= 0.5 ? f.p : 1 - f.p) * 100).toFixed(1)}%</div>
        <div class="bias" style="--c:{dirOf(f.p, f.lab) === 0 ? 'var(--muted)' : probColor(f.p)}">{biasWord(f.p, f.lab)}{dirOf(f.p, f.lab) ? ' BIAS' : ''} · {$fh}</div>
        {#if conviction(f.p) < 2}<div class="hint">{dirOf(f.p, f.lab) === 0 ? 'Close to a coin flip: no meaningful lean right now.' : 'A small lean: close to a coin flip.'}</div>{/if}
        <div class="sub">{((f.p >= 0.5 ? f.p : 1 - f.p) * 100).toFixed(1)}% chance the {m.short} perpetual closes <b style="color:{probColor(f.p)}">{f.p >= 0.5 ? 'higher' : 'lower'}</b> in {$fh}</div>
        {#if sk?.accuracy != null}
          <div class="acc" title="Measured in walk-forward tests 2024–2026 on data the model never saw">
            Tested: right <b>{(sk.accuracy * 100).toFixed(1)}%</b> overall{#if sk.conf55_hit} · <b>{(sk.conf55_hit * 100).toFixed(1)}%</b> when ≥55%{/if}{#if f.tier === 1} · weak skill{/if}
          </div>
        {/if}
      {:else}
        <div class="pbig faint">No edge</div><div class="sub">no tested skill for {m.short} at {$fh}; the ranges still apply</div>
      {/if}
    </div>
  </div>
  {#if f}
    <div class="blk rng">
      <div><span class="lab">68% range</span><b class="num">{px(f.lo68, m.digits)} – {px(f.hi68, m.digits)}</b></div>
      <div><span class="lab">95% range</span><b class="num">{px(f.lo95, m.digits)} – {px(f.hi95, m.digits)}</b></div>
      <div><span class="lab" title="Futures taker fee both ways is about 0.10%">Typical move</span><b class="num">±{(f.move_bp / 100).toFixed(2)}%{#if !f.tradable}<em> below fees</em>{/if}</b></div>
    </div>
  {/if}

  <!-- reasons -->
  <div class="blk">
    <div class="bt">Why <span>the inputs pushing the {$fh} forecast hardest</span></div>
    {#if f?.show && reasons.length}
      <div class="rs">
        {#each reasons as r (r.t)}
          <div class="r" in:fade={{ duration: 350 }}>
            <span class="ic" class:up={r.push > 0} class:down={r.push < 0}>{r.push > 0 ? '↑' : '↓'}</span>
            <span class="tx">{r.t}</span>
            <span class="wb"><i class:up={r.push > 0} class:down={r.push < 0} style="width:{(Math.abs(r.w) / maxW) * 100}%"></i></span>
            <span class="ly">{r.layer}</span>
          </div>
        {/each}
      </div>
    {:else}
      <div class="note">Reasons appear for horizons with tested skill.</div>
    {/if}
  </div>

  <!-- levels -->
  <div class="blk">
    <div class="bt">Support &amp; resistance <span>reach = measured chance price trades there</span></div>
    <div class="lvt">
      <span class="lh"></span><span class="lh r">price</span><span class="lh r">away</span><span class="lh r">{rh}</span><span class="lh r">1d</span>
      {#each (lv?.resistance || []).slice().reverse() as x, i}
        <span class="tag res">R{(lv?.resistance?.length || 0) - i} <em>{'●'.repeat(x.strength)}<s>{'●'.repeat(3 - x.strength)}</s></em></span>
        <span class="num pr r" title={x.sources.join(' · ')}>{px(x.price, m.digits)}</span>
        <span class="num r dim">+{dist(x.price).toFixed(2)}%</span><span class="num r">{reach(x, rh)}</span><span class="num r">{reach(x, '1d')}</span>
      {/each}
      <span class="tag now">PRICE</span><span class="num pr r nowp">{px(m.price, m.digits)}</span><span></span><span></span><span></span>
      {#each lv?.support || [] as x, i}
        <span class="tag sup">S{i + 1} <em>{'●'.repeat(x.strength)}<s>{'●'.repeat(3 - x.strength)}</s></em></span>
        <span class="num pr r" title={x.sources.join(' · ')}>{px(x.price, m.digits)}</span>
        <span class="num r dim">{dist(x.price).toFixed(2)}%</span><span class="num r">{reach(x, rh)}</span><span class="num r">{reach(x, '1d')}</span>
      {/each}
    </div>
    {#if hold?.res?.level}<div class="note">Tested 2024–26: after a touch, price turned back {(hold.res.level.held60 * 100).toFixed(0)}% (resistance) and {(hold.sup.level.held60 * 100).toFixed(0)}% (support) of the time — the same as at arbitrary prices. Treat levels as reference prices; the reach chances are measured.</div>{/if}
  </div>

  <!-- buyers & sellers -->
  <div class="blk">
    <div class="bt">Strong buyers &amp; sellers {#if bk?.sim}<span class="sim">simulated in replay</span>{/if}</div>
    {#if bk}
      <div class="imb">
        <span class="lab">Order book ±0.25%</span>
        <span class="ib"><i style="width:{(bk['imb_0.25'] ?? 0.5) * 100}%"></i></span>
        <span class="num">{bk['imb_0.25'] != null ? `${Math.round(bk['imb_0.25'] * 100)}% bids` : '—'}</span>
        <span class="lab">Order book ±1%</span>
        <span class="ib"><i style="width:{(bk.imb_1 ?? 0.5) * 100}%"></i></span>
        <span class="num">{bk.imb_1 != null ? `${Math.round(bk.imb_1 * 100)}% bids` : '—'}</span>
      </div>
      <div class="walls">
        <div><div class="wh up">Buy walls (resting bids)</div>
          {#each bk.bid as w}<div class="w"><span class="num">{px(w.price, m.digits)}</span><b class="num up">${usd(w.usd).slice(2)}</b><span class="num faint">{w.dist.toFixed(2)}%{#if w.age != null} · {w.age < 60 ? `${w.age}s` : `${Math.round(w.age / 60)}m`}{/if}</span></div>{:else}<div class="faint">none stand out</div>{/each}</div>
        <div><div class="wh down">Sell walls (resting asks)</div>
          {#each bk.ask as w}<div class="w"><span class="num">{px(w.price, m.digits)}</span><b class="num down">${usd(w.usd).slice(2)}</b><span class="num faint">+{w.dist.toFixed(2)}%{#if w.age != null} · {w.age < 60 ? `${w.age}s` : `${Math.round(w.age / 60)}m`}{/if}</span></div>{:else}<div class="faint">none stand out</div>{/each}</div>
      </div>
    {:else}
      <div class="note">Order book loads a few seconds after start.</div>
    {/if}
    <div class="bigh"><span class="lab">Big trades, 15 min <em>(≥ ${usd($bigUsd[sym] || 0).slice(2)})</em></span>
      <span class="ib two"><i style="width:{pctOf(b15[0], b15[1]) * 100}%"></i></span>
      <span class="num"><b class="up">{usd(b15[0]).slice(1)}</b> / <b class="down">{usd(b15[1]).slice(1)}</b></span></div>
    <div class="bigl">
      {#each big as b (b.ts + b.side + b.usd)}
        <div class="bt2" class:buy={b.side === 'buy'} in:fly={{ y: -8, duration: 300 }}>
          <span class="sd">{b.side === 'buy' ? 'BUY' : 'SELL'}</span><b class="num">${usd(b.usd).slice(2)}</b><span class="num">@ {px(b.price, m.digits)}</span><span class="num faint">{ago(Math.max(0, now() - b.ts / 1000))}</span>
        </div>
      {:else}<div class="faint sm">No big trades yet.</div>{/each}
    </div>
    {#if zones}
      <div class="zl">
        <span class="lab">24h volume zones</span>
        {#each zones.buyers as z}<span class="zc up">Buyers {px(z.price, m.digits)} <b>{usd(z.net)}</b></span>{/each}
        {#each zones.sellers as z}<span class="zc down">Sellers {px(z.price, m.digits)} <b>{usd(z.net)}</b></span>{/each}
      </div>
    {/if}
    <div class="note">Live order flow describes what is happening; it is not part of the tested forecast, and resting orders can be pulled at any time.</div>
  </div>

  <!-- positioning -->
  <div class="blk kv">
    <span>Open interest, 1h</span><b class="num" class:up={(m.oiChg1h ?? 0) > 0} class:down={(m.oiChg1h ?? 0) < 0}>{pct(m.oiChg1h != null ? m.oiChg1h * 100 : null)}</b>
    <span>Long / short accounts</span><b class="num">{m.lsRatio != null ? m.lsRatio.toFixed(2) : '—'}</b>
    <span>Funding rate{#if m.nextFunding} · next in {fmtLeft(m.nextFunding / 1000 - $serverTime)}{/if}</span><b class="num" class:up={(m.funding ?? 0) > 0} class:down={(m.funding ?? 0) < 0}>{m.funding != null ? (m.funding * 100).toFixed(4) + '%' : '—'}</b>
    <span>Taker flow, 60 s</span><b class="num" class:up={m.b60 > m.s60} class:down={m.b60 < m.s60}>{usd(m.b60 - m.s60)}</b>
  </div>
</aside>
<style>
  .ol { overflow-y: auto; min-height: 0; }
  .blk { padding: 14px 18px; border-bottom: 1px solid var(--line); }
  .head { display: flex; align-items: center; gap: 14px; }
  .pbig { display: flex; align-items: center; gap: 10px; font-size: 34px; font-weight: 800; letter-spacing: -1px; line-height: 1.05; transition: color .6s; }
  .sub { color: var(--muted); font-size: 12.5px; }
  .hint { font-size: 11px; color: var(--faint); margin-bottom: 2px; }
  .bias { display: inline-block; margin: 4px 0 3px; padding: 2px 9px; border-radius: 6px; font: 800 11px var(--sans); letter-spacing: 1.5px;
    color: var(--c); background: color-mix(in srgb, var(--c) 14%, transparent); border: 1px solid color-mix(in srgb, var(--c) 45%, transparent); }
  .acc { margin-top: 6px; font-size: 11px; color: var(--faint); } .acc b { color: var(--text); font-weight: 600; }
  .rng { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding-top: 10px; padding-bottom: 12px; }
  .rng div { display: flex; flex-direction: column; } .rng b { font-size: 12px; font-weight: 600; } .rng em { font-style: normal; color: var(--faint); font-size: 10px; margin-left: 4px; }
  .lab { font: 600 9.5px var(--sans); letter-spacing: 1.1px; text-transform: uppercase; color: var(--faint); }
  .lab em { font-style: normal; text-transform: none; letter-spacing: 0; }
  .bt { font: 700 11px var(--sans); letter-spacing: 1.3px; text-transform: uppercase; color: var(--text); margin-bottom: 10px; display: flex; align-items: baseline; gap: 8px; }
  .bt span { text-transform: none; letter-spacing: 0; color: var(--faint); font-weight: 500; font-size: 11px; }
  .bt .sim { color: var(--res); border: 1px dashed var(--res); border-radius: 5px; padding: 0 5px; font-size: 10px; }
  .rs { display: flex; flex-direction: column; gap: 7px; }
  .r { display: grid; grid-template-columns: 18px 1fr 64px 64px; gap: 8px; align-items: center; font-size: 12.5px; }
  .ic { width: 18px; height: 18px; border-radius: 5px; display: grid; place-items: center; font-size: 13px; font-weight: 800; }
  .ic.up { background: rgba(var(--up-rgb), .15); } .ic.down { background: rgba(var(--down-rgb), .15); }
  .tx { color: var(--text); line-height: 1.3; }
  .wb { height: 5px; border-radius: 3px; background: rgba(148,163,214,.08); overflow: hidden; }
  .wb i { display: block; height: 100%; border-radius: 3px; transition: width .6s ease; }
  .wb i.up { background: var(--up); } .wb i.down { background: var(--down); }
  .ly { font-size: 10px; color: var(--faint); text-align: right; text-transform: capitalize; }
  .lvt { display: grid; grid-template-columns: 62px 1fr 64px 44px 44px; gap: 6px 8px; align-items: center; font-size: 12.5px; }
  .lh { font: 600 9px var(--sans); letter-spacing: 1px; text-transform: uppercase; color: var(--faint); } .r { text-align: right; }
  .tag { font: 800 11px var(--sans); } .tag em { font-style: normal; font-size: 7px; letter-spacing: 1px; margin-left: 2px; vertical-align: 2px; } .tag s { text-decoration: none; opacity: .25; }
  .tag.res { color: var(--res); } .tag.sup { color: var(--sup); } .tag.now { color: var(--text); font-size: 10px; letter-spacing: 1px; }
  .pr { font-weight: 600; cursor: help; } .nowp { color: var(--text); padding: 2px 0; border-top: 1px dashed var(--line3); border-bottom: 1px dashed var(--line3); }
  .note { font-size: 10.5px; color: var(--faint); line-height: 1.55; margin-top: 10px; }
  .imb { display: grid; grid-template-columns: 120px 1fr 70px; gap: 6px 10px; align-items: center; font-size: 11.5px; }
  .ib { position: relative; height: 7px; border-radius: 4px; background: rgba(var(--down-rgb), .6); overflow: hidden; }
  .ib i { position: absolute; left: 0; top: 0; bottom: 0; background: var(--up); transition: width .7s ease; }
  .ib::after { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: rgba(255,255,255,.6); }
  .walls { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 12px; }
  .wh { font: 700 10px var(--sans); letter-spacing: .6px; text-transform: uppercase; margin-bottom: 4px; }
  .w { display: grid; grid-template-columns: 1fr auto; gap: 0 6px; font-size: 11.5px; padding: 3px 0; border-bottom: 1px solid var(--line); }
  .w b { font-size: 12px; } .w .faint { grid-column: 1 / 3; font-size: 10px; }
  .bigh { display: grid; grid-template-columns: 1fr 90px auto; gap: 10px; align-items: center; margin-top: 14px; font-size: 11.5px; }
  .bigl { display: flex; flex-direction: column; gap: 3px; margin-top: 8px; }
  .bt2 { display: grid; grid-template-columns: 40px 64px 1fr 34px; gap: 8px; font-size: 11.5px; padding: 3px 8px; border-radius: 6px; background: rgba(var(--down-rgb), .07); }
  .bt2.buy { background: rgba(var(--up-rgb), .07); }
  .sd { font: 800 10px var(--sans); color: var(--down); letter-spacing: .5px; align-self: center; } .bt2.buy .sd { color: var(--up); }
  .sm { font-size: 11px; }
  .zl { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 12px; }
  .zc { font-size: 11px; padding: 2px 8px; border-radius: 99px; border: 1px solid currentColor; }
  .zc b { font-family: var(--mono); font-weight: 600; }
  .kv { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; font-size: 12px; }
  .kv span { color: var(--muted); } .kv b { text-align: right; font-weight: 500; }
</style>
