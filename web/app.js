/* XAHOO terminal UI — vanilla JS, no build step. */
(() => {
  "use strict";
  const IST = 19800;                         // seconds; chart axis is shown in IST
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const st = { sym: "XAUUSD", tf: "5m", signals: [], selected: null, overview: null, stats: null };
  const DIG = { XAUUSD: 2, XAGUSD: 3 };
  const CONTRACT = { XAUUSD: 100, XAGUSD: 5000 };
  const SETUP = { impulse_pullback: "Impulse→EMA12→break", ema12_pullback: "EMA12 pullback", ema200_retest: "EMA200 retest", range: "Range edge", sweep: "Liq. sweep" };
  const px = (v, s) => v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: DIG[s] ?? 2, maximumFractionDigits: DIG[s] ?? 2 });
  const sgn = (v, d = 2) => (v > 0 ? "+" : "") + Number(v).toFixed(d);
  const cls = v => v > 0.0001 ? "up" : v < -0.0001 ? "dn" : "flat";
  const tIST = (t, withDate = true) => {
    const d = new Date((t + IST) * 1000).toISOString();
    return withDate ? d.slice(5, 10) + " " + d.slice(11, 16) : d.slice(11, 19);
  };
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path) {
    const r = await fetch(path, { credentials: "same-origin" });
    if (r.status === 401) { location.replace("/login"); throw new Error("login required"); }
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }


  // ------------------------------------------------------------ log
  function log(msg, kind = "") {
    const el = $("#log");
    const d = document.createElement("div");
    d.innerHTML = `<span class="t">${tIST(Math.floor(Date.now() / 1000), false)}</span><span class="${kind}">${msg}</span>`;
    el.prepend(d);
    while (el.children.length > 200) el.lastChild.remove();
  }

  // ------------------------------------------------------------ theme
  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("xahoo-theme", t); } catch (e) { /* storage unavailable */ }
    if (chart) applyChartTheme();
    if (eqChart) eqChart.applyOptions(chartTheme());
  }
  function initTheme() {
    let t = null;
    try { t = localStorage.getItem("xahoo-theme"); } catch (e) { /* ignore */ }
    document.documentElement.dataset.theme = t || "dark";
    $("#theme").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  }

  // ------------------------------------------------------------ chart
  let chart, candleS, fastS, slowS, priceLines = [];
  const chartTheme = () => ({
    layout: { background: { color: css("--panel") }, textColor: css("--dim"), fontFamily: css("--font"), fontSize: 11 },
    grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
    rightPriceScale: { borderColor: css("--line2") },
    timeScale: { borderColor: css("--line2"), timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
  });
  function applyChartTheme() {
    chart.applyOptions(chartTheme());
    candleS.applyOptions({ upColor: css("--green"), downColor: css("--red"), wickUpColor: css("--green"), wickDownColor: css("--red"), borderVisible: false });
    fastS.applyOptions({ color: css("--amber") });
    slowS.applyOptions({ color: css("--violet") });
  }
  function initChart() {
    const el = $("#chart");
    chart = LightweightCharts.createChart(el, { ...chartTheme(), autoSize: true });
    candleS = chart.addCandlestickSeries({});
    fastS = chart.addLineSeries({ lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    slowS = chart.addLineSeries({ lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    applyChartTheme();
  }
  async function loadChart(around) {
    const tfSec = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400 }[st.tf];
    const end = around ? `&end=${around + tfSec * 150}` : "";
    const d = await api(`/api/candles?symbol=${st.sym}&tf=${st.tf}&limit=600${end}`);
    const t = d.t.map(x => x + IST);
    // live candle state: only when showing the latest data (not a past signal)
    const n = t.length;
    st.liveChart = !around && n > 1 ? { sym: st.sym, tf: st.tf, tfSec,
      bar: { time: t[n - 1], open: d.o[n - 1], high: d.h[n - 1], low: d.l[n - 1], close: d.c[n - 1] },
      fastPrev: d.ema_fast[n - 2], slowPrev: d.ema_slow[n - 2] } : null;
    candleS.setData(t.map((x, i) => ({ time: x, open: d.o[i], high: d.h[i], low: d.l[i], close: d.c[i] })));
    fastS.setData(t.map((x, i) => ({ time: x, value: d.ema_fast[i] })));
    slowS.setData(t.map((x, i) => ({ time: x, value: d.ema_slow[i] })));
    candleS.applyOptions({ priceFormat: { type: "price", precision: DIG[st.sym], minMove: 1 / 10 ** DIG[st.sym] } });
    drawMarkers(t[0]);
    drawLevels();
  }
  function drawMarkers(t0) {
    const tfSec = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400 }[st.tf];
    const ms = st.signals
      .filter(s => s.symbol === st.sym && (s.tf === st.tf || tfSec > 900))
      .map(s => {
        const bar = Math.floor((s.close_time - 1) / tfSec) * tfSec + IST; // bar containing the signal close
        return { time: bar, position: s.dir === 1 ? "belowBar" : "aboveBar", color: s.dir === 1 ? css("--green") : css("--red"),
                 shape: s.dir === 1 ? "arrowUp" : "arrowDown", text: `${s.grade}` };
      })
      .filter(m => m.time >= t0)
      .sort((a, b) => a.time - b.time);
    candleS.setMarkers(ms);
  }
  function drawLevels() {
    priceLines.forEach(l => candleS.removePriceLine(l));
    priceLines = [];
    const s = st.selected;
    if (!s || s.symbol !== st.sym) return;
    const add = (price, color, title, style = 2) => priceLines.push(candleS.createPriceLine({ price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title }));
    add(s.entry, css("--blue"), "ENTRY", 0);
    if (s.add_price) add(s.add_price, css("--amber"), "ADD LOT 2", 1);
    add(s.sl, css("--red"), "SL");
    if (s.tp1 === s.tp3) add(s.tp1, css("--green"), "TARGET");
    else { add(s.tp1, css("--green"), "TP1"); add(s.tp2, css("--green"), "TP2"); add(s.tp3, css("--green"), "TP3"); }
  }

  // ------------------------------------------------------------ overview
  function renderTickers(o) {
    $("#tickers").innerHTML = Object.entries(o.symbols).map(([s, v]) => `
      <div class="tick ${s === st.sym ? "on" : ""}" data-sym="${s}">
        <span class="sym">${s}</span>
        <span class="px">${px(v.price, s)}</span>
        <span class="${cls(v.change)}">${sgn(v.change, DIG[s])} (${sgn(v.change_pct)}%)</span>
        <span class="kv">24H H <b>${px(v.day_high, s)}</b></span><span class="kv">L <b>${px(v.day_low, s)}</b></span>
        <span class="kv">ATR5m <b>${v.matrix["5m"].atr}</b></span><span class="kv">SPRD <b>${v.spread}</b></span>
      </div>`).join("");
    $$(".tick").forEach(el => el.onclick = () => setSym(el.dataset.sym));
  }
  function renderMatrix(o) {
    const tfs = ["1m", "5m", "15m", "1h", "4h"];
    const arrow = b => b === 1 ? `<span class="arrow up">▲</span>` : b === -1 ? `<span class="arrow dn">▼</span>` : `<span class="arrow flat">■</span>`;
    let h = `<table class="mx"><thead><tr><th>TF</th><th>BIAS</th><th>Δ12</th><th>Δ200</th><th>ADX</th></tr></thead><tbody>`;
    for (const [s, v] of Object.entries(o.symbols)) {
      h += `<tr class="symrow"><td colspan="5">${s}</td></tr>`;
      for (const tf of tfs) {
        const m = v.matrix[tf];
        h += `<tr><td>${tf}</td><td>${arrow(m.bias)}</td><td class="${cls(m.d_fast_atr)}">${sgn(m.d_fast_atr)}</td><td class="${cls(m.d_slow_atr)}">${sgn(m.d_slow_atr)}</td><td>${m.adx}</td></tr>`;
      }
    }
    $("#matrix").innerHTML = h + "</tbody></table>";
  }
  function renderSession(o) {
    for (const k of ["asia", "london", "newyork"]) $(`#sess-${k}`).classList.toggle("on", !!o.session[k]);
  }

  // ------------------------------------------------------------ signals
  const STATE = { OPEN: "OPEN", ADDED: "LOT 2 IN", RISK_FREE: "RISK-FREE" };
  const resTxt = s => s.result ? `<span class="${cls(s.r)}">${sgn(s.r)}R</span>` : `<span class="up">${STATE[s.state] || "OPEN"}</span>`;
  const srcTag = s => s.source === "live" ? `<span class="gr gA">LIVE</span>` : `<span class="gr gB" title="backtest replay">BT</span>`;
  function renderFeed() {
    const list = st.signals.slice(0, 80);
    $("#feedcount").textContent = `${st.signals.length} in window`;
    const forming = (st.watch || []).map(x => `
      <div class="sig forming">
        <span class="side" style="color:var(--amber)">${x.dir === 1 ? "BUY" : "SELL"}?</span>
        <span>${x.symbol.slice(0, 3)} · 5m · <span class="gr" style="color:var(--amber)">FORMING</span></span>
        <span class="res" style="color:var(--amber)">≤ ${x.bars_left * 5}m</span>
        <span class="meta">trigger: 5m close ${x.dir === 1 ? "above" : "below"} ${px(x.trigger, x.symbol)} · stop ≈ ${px(x.sl_est, x.symbol)} · impulse ${x.impulse_atr}× ATR</span>
      </div>`).join("");
    $("#feed").innerHTML = forming + list.map(s => `
      <div class="sig ${st.selected && st.selected.id === s.id ? "sel" : ""}" data-id="${esc(s.id)}">
        <span class="side ${s.dir === 1 ? "up" : "dn"}">${s.dir === 1 ? "BUY" : "SELL"}</span>
        <span>${s.symbol.slice(0, 3)} · ${s.tf} · ${srcTag(s)}</span>
        <span class="res">${resTxt(s)}</span>
        <span class="meta">${tIST(s.close_time)} · ${SETUP[s.setup] || s.setup} · @ ${px(s.entry, s.symbol)}${s.news_impulse ? " · 📰 NEWS" : ""}</span>
        <span class="meta" style="grid-column:3;text-align:right">${s.result || ""}</span>
      </div>`).join("") || `<div class="pad dim">No signals in window.</div>`;
    $$(".sig").forEach(el => el.onclick = () => select(el.dataset.id));
  }
  function select(id) {
    const s = st.signals.find(x => x.id === id);
    if (!s) return;
    st.selected = s;
    st.sym = s.symbol; st.tf = s.tf; syncSegs();
    loadChart(s.close_time).then(() => focusSignal(s));
    renderFeed();
    openDrawer(s);
  }
  function focusSignal(s) {
    const tfSec = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400 }[st.tf];
    const c = s.close_time + IST;
    chart.timeScale().setVisibleRange({ from: c - tfSec * 60, to: c + tfSec * 40 });
  }
  function openDrawer(s) {
    const R = v => Math.abs(v - s.entry) / s.risk;
    const comps = Object.entries(s.components || {});
    $("#d-id").textContent = s.id;
    $("#d-body").innerHTML = `
      <div class="big"><span class="${s.dir === 1 ? "up" : "dn"}">${s.dir === 1 ? "BUY" : "SELL"} ${s.symbol}</span>
        <span class="gr g${s.grade}">${s.grade}</span><span class="dim">${Math.round(s.score)}/100 · ${s.tf}</span></div>
      <div class="dl">
        <span class="k">Setup</span><span></span><span class="v">${SETUP[s.setup] || s.setup}</span>
        <span class="k">Signal time</span><span></span><span class="v">${tIST(s.close_time)} IST</span>
        <span class="k">Entry</span><span></span><span class="v">${px(s.entry, s.symbol)}</span>
        ${s.add_price ? `<span class="k">Add lot 2</span><span class="dim">EMA12</span><span class="v" style="color:var(--amber)">${px(s.add_price, s.symbol)}</span>` : ""}
        <span class="k">Stop loss</span><span class="dim">-${px(s.risk, s.symbol)}</span><span class="v dn">${px(s.sl, s.symbol)}</span>
        ${s.tp1 === s.tp3 ? `<span class="k">Target</span><span class="dim">${R(s.tp1).toFixed(1)}R</span><span class="v up">${px(s.tp1, s.symbol)}</span>` : `
        <span class="k">TP1</span><span class="dim">${R(s.tp1).toFixed(1)}R</span><span class="v up">${px(s.tp1, s.symbol)}</span>
        <span class="k">TP2</span><span class="dim">${R(s.tp2).toFixed(1)}R</span><span class="v up">${px(s.tp2, s.symbol)}</span>
        <span class="k">TP3</span><span class="dim">${R(s.tp3).toFixed(1)}R</span><span class="v up">${px(s.tp3, s.symbol)}</span>`}
        <span class="k">Bias 4h / 1h</span><span></span><span class="v">${["▼", "■", "▲"][s["4h_bias"] + 1]} / ${["▼", "■", "▲"][s["1h_bias"] + 1]}</span>
        <span class="k">Session</span><span></span><span class="v">${s.session}${s.overlap ? " (overlap)" : ""}</span>
      </div>
      <div class="ph">OUTCOME</div>
      <div class="dl">
        <span class="k">Result</span><span></span><span class="v">${s.result || "OPEN"} ${s.result ? `· ${resTxt(s)}` : ""}</span>
        <span class="k">Lots</span><span></span><span class="v">${s.lots ?? (s.state === "ADDED" || s.state === "RISK_FREE" ? 2 : 1)}</span>
        <span class="k">Source</span><span></span><span class="v">${s.source === "live" ? "LIVE signal" : "Backtest replay"}</span>
        <span class="k">Exit</span><span></span><span class="v">${s.exit_time ? tIST(s.exit_time) + " @ " + px(s.exit_price, s.symbol) : "—"}</span>
        <span class="k">Duration</span><span></span><span class="v">${s.minutes ?? "—"} min</span>
        <span class="k">Best / worst</span><span></span><span class="v"><span class="up">+${s.mfe_r}R</span> / <span class="dn">-${s.mae_r}R</span></span>
      </div>
      <div class="ph">CONFLUENCE SCORE</div>
      ${comps.map(([k, v]) => `<div class="comp"><span class="dim">${k}</span><span class="bar"><i style="width:${v * 100}%"></i></span><span>${Math.round(v * 100)}</span></div>`).join("")}
      <div class="pad dim small">${s.add_price ? "Management: lot 1 at entry · lot 2 at the add zone (EMA12) · one stop · at +1R move stop to average entry · target 2R from entry." : "Management: 50% at TP1 → SL to entry · 25% TP2 · 25% TP3."}</div>`;
    $("#drawer").hidden = false;
  }

  // ------------------------------------------------------------ KPIs & analytics
  function kpiHtml(sm) {
    const k = (label, v, c = "") => `<div class="kpi"><div class="k">${label}</div><div class="v ${c}">${v}</div></div>`;
    if (!sm || !sm.signals) return k("SIGNALS", 0);
    return [
      k("SIGNALS", sm.signals), k("PER DAY", sm.per_day), k("TP1 HIT", sm.tp1_hit_rate + "%"),
      k("WIN RATE", sm.win_rate + "%"), k("LOSS RATE", sm.loss_rate + "%"),
      k("AVG R", sgn(sm.avg_r, 3), cls(sm.avg_r)), k("NET R", sgn(sm.total_r, 1), cls(sm.total_r)),
      k("PROFIT F.", sm.profit_factor, sm.profit_factor >= 1 ? "up" : "dn"), k("MAX DD", sm.max_dd_r + "R", "dn"),
    ].join("");
  }
  let eqChart;
  function renderAnalytics(s) {
    if (!eqChart) {
      eqChart = LightweightCharts.createChart($("#equity"), { ...chartTheme(), autoSize: true });
      eqChart.series = eqChart.addBaselineSeries({ baseValue: { type: "price", price: 0 } });
    }
    const seen = new Set();
    const eq = (s.equity || []).map(p => { let t = p.t + IST; while (seen.has(t)) t++; seen.add(t); return { time: t, value: p.v }; }).sort((a, b) => a.time - b.time);
    eqChart.series.setData(eq);
    eqChart.timeScale().fitContent();
    const names = { symbol: "BY SYMBOL", tf: "BY TIMEFRAME", setup: "BY SETUP", grade: "BY GRADE", session: "BY SESSION", hour_ist: "BY HOUR (IST)" };
    $("#agrid").innerHTML = Object.entries(s.tables || {}).map(([name, rows]) => `
      <div class="panel"><div class="ph">${names[name]}</div><div class="tablewrap"><table class="tbl">
        <thead><tr><th>${name === "hour_ist" ? "HOUR" : "KEY"}</th><th>N</th><th>TP1%</th><th>WIN%</th><th>AVG R</th><th>NET R</th></tr></thead>
        <tbody>${rows.map(r => `<tr><td>${esc(SETUP[r.key] || r.key)}</td><td>${r.n}</td><td>${r["tp1_hit%"]}</td><td>${r["win%"]}</td>
          <td class="${cls(r.avg_r)}">${sgn(r.avg_r, 3)}</td><td class="${cls(r.total_r)}">${sgn(r.total_r, 1)}</td></tr>`).join("")}</tbody>
      </table></div></div>`).join("");
  }

  function renderTable() {
    const f = { sym: $("#f-sym").value, tf: $("#f-tf").value, grade: $("#f-grade").value, res: $("#f-res").value };
    const rows = st.signals.filter(s => (!f.sym || s.symbol === f.sym) && (!f.tf || s.tf === f.tf) && (!f.grade || s.grade === f.grade) && (!f.res || s.result === f.res));
    $("#sigtable").innerHTML = `<thead><tr><th>TIME (IST)</th><th>SYMBOL</th><th>SIDE</th><th>SETUP</th><th>TF</th><th>GRADE</th><th>SCORE</th><th>ENTRY</th><th>SL</th><th>TP1</th><th>RESULT</th><th>R</th><th>MIN</th></tr></thead>
      <tbody>${rows.map(s => `<tr data-id="${esc(s.id)}"><td>${tIST(s.close_time)}</td><td>${s.symbol}</td><td class="${s.dir === 1 ? "up" : "dn"}">${s.dir === 1 ? "BUY" : "SELL"}</td>
        <td>${SETUP[s.setup] || s.setup}</td><td>${s.tf}</td><td><span class="gr g${s.grade}">${s.grade}</span></td><td>${Math.round(s.score)}</td>
        <td>${px(s.entry, s.symbol)}</td><td>${px(s.sl, s.symbol)}</td><td>${px(s.tp1, s.symbol)}</td><td>${s.result || "OPEN"}</td>
        <td class="${cls(s.r)}">${s.r == null ? "" : sgn(s.r)}</td><td>${s.minutes ?? ""}</td></tr>`).join("")}</tbody>`;
    $$("#sigtable tbody tr").forEach(tr => tr.onclick = () => { showView("terminal"); select(tr.dataset.id); });
    st.filtered = rows;
  }
  function exportCsv() {
    const rows = st.filtered || st.signals;
    const cols = ["id", "symbol", "tf", "dir", "setup", "grade", "score", "entry", "sl", "tp1", "tp2", "tp3", "result", "r", "minutes"];
    const csv = [cols.join(","), ...rows.map(r => cols.map(c => r[c] ?? "").join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "xahoo-signals.csv";
    a.click();
  }

  // ------------------------------------------------------------ calc
  function calc() {
    const acc = +$("#acc").value, pct = +$("#riskpct").value, sl = +$("#sldist").value, sym = $("#calcsym").value;
    if (!(acc > 0 && pct > 0 && sl > 0)) { $("#calcout").textContent = "—"; return; }
    const riskUsd = acc * pct / 100;
    const lots = riskUsd / (sl * CONTRACT[sym]);
    $("#calcout").innerHTML = `${lots.toFixed(2)} lots <span class="dim small">risk $${riskUsd.toFixed(0)}</span>`;
  }

  // ------------------------------------------------------------ navigation
  function syncSegs() {
    $$("#symseg button").forEach(b => b.classList.toggle("on", b.dataset.sym === st.sym));
    $$("#tfseg button").forEach(b => b.classList.toggle("on", b.dataset.tf === st.tf));
    $$(".tick").forEach(t => t.classList.toggle("on", t.dataset.sym === st.sym));
  }
  function setSym(s) { st.sym = s; syncSegs(); loadChart(); }
  function setTf(t) { st.tf = t; syncSegs(); loadChart(); }
  function showView(v) {
    $$(".views button").forEach(b => b.classList.toggle("on", b.dataset.view === v));
    $$(".view").forEach(el => el.hidden = el.id !== `view-${v}`);
    $("#tickers").hidden = v !== "terminal";
    if (v === "signals") renderTable();
    if (v === "analytics" && st.stats) renderAnalytics(st.stats);
  }
  function runCmd(c) {
    c = c.trim().toLowerCase();
    if (["xau", "gold"].includes(c)) setSym("XAUUSD");
    else if (["xag", "silver"].includes(c)) setSym("XAGUSD");
    else if (["1m", "5m", "15m", "1h", "4h"].includes(c)) setTf(c);
    else if (["terminal", "signals", "analytics"].includes(c)) showView(c);
    else if (["strategy", "settings", "params"].includes(c)) showView("settings");
    else if (c === "theme") $("#theme").click();
    else if (c) log(`unknown command: ${esc(c)}`, "dn");
  }

  function bind() {
    $$(".views button").forEach(b => b.onclick = () => showView(b.dataset.view));
    $$("#symseg button").forEach(b => b.onclick = () => setSym(b.dataset.sym));
    $$("#tfseg button").forEach(b => b.onclick = () => setTf(b.dataset.tf));
    $("#d-close").onclick = () => { $("#drawer").hidden = true; st.selected = null; drawLevels(); loadChart(); };
    ["#f-sym", "#f-tf", "#f-grade", "#f-res"].forEach(s => $(s).onchange = renderTable);
    $("#csv").onclick = exportCsv;
    ["#acc", "#riskpct", "#sldist", "#calcsym"].forEach(s => $(s).oninput = calc);
    document.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#cmdk").hidden = false; $("#cmdin").value = ""; $("#cmdin").focus(); }
      else if (e.key === "Escape") {
        if (!$("#cmdk").hidden || !$("#drawer").hidden) { $("#cmdk").hidden = true; $("#drawer").hidden = true; }
        else { const t = $("#toasts").firstElementChild; if (t) t.remove(); }       // Esc closes the newest notification
      }
      else if (/^F[1-4]$/.test(e.key)) { e.preventDefault(); showView(["terminal", "signals", "analytics", "settings"][+e.key[1] - 1]); }
    });
    $("#cmdin").addEventListener("keydown", e => { if (e.key === "Enter") { runCmd(e.target.value); $("#cmdk").hidden = true; } });
    $("#cmdk").onclick = e => { if (e.target.id === "cmdk") $("#cmdk").hidden = true; };
  }

  function tickClock(now) {
    $("#clock").textContent = tIST(now, false) + " IST";
  }

  // ------------------------------------------------------------ live chart: update the forming candle every tick
  const AF = 2 / 13, AS = 2 / 201;                 // EMA12 / EMA200 smoothing
  let resyncTimer = null;
  function liveTick(price, tsec) {
    const L = st.liveChart;
    if (!L || L.sym !== st.sym || L.tf !== st.tf || !isFinite(price)) return;
    const bucket = Math.floor(tsec / L.tfSec) * L.tfSec + IST;
    if (bucket < L.bar.time) return;
    if (bucket > L.bar.time) {                      // previous candle closed: roll the EMAs forward, open a new candle
      L.fastPrev = L.fastPrev + AF * (L.bar.close - L.fastPrev);
      L.slowPrev = L.slowPrev + AS * (L.bar.close - L.slowPrev);
      L.bar = { time: bucket, open: L.bar.close, high: Math.max(L.bar.close, price), low: Math.min(L.bar.close, price), close: price };
      clearTimeout(resyncTimer);
      resyncTimer = setTimeout(() => { if (st.liveChart) loadChart(); }, 15000);   // re-sync with server candles
    } else {
      L.bar.high = Math.max(L.bar.high, price); L.bar.low = Math.min(L.bar.low, price); L.bar.close = price;
    }
    candleS.update({ ...L.bar });
    fastS.update({ time: L.bar.time, value: L.fastPrev + AF * (price - L.fastPrev) });
    slowS.update({ time: L.bar.time, value: L.slowPrev + AS * (price - L.slowPrev) });
  }
  window.__xahooLive = () => st.liveChart && { ...st.liveChart.bar };      // read-only probe for tests
  async function pollTicks() {
    try {
      const f = await api("/api/feed");
      const q = (f.quotes || {})[st.sym];
      if (q) liveTick(q.bid, q.ts);
      for (const [sym, qq] of Object.entries(f.quotes || {})) {        // header prices tick too
        const el = document.querySelector(`.tick[data-sym="${sym}"] .px`);
        if (el) el.textContent = px(qq.bid, sym);
      }
    } catch (e) { /* next tick */ }
  }

  // ------------------------------------------------------------ first start: history still downloading
  function renderWarming(o) {
    const pr = o.progress || { done: 0, total: 0, pct: 0 };
    const syms = Object.keys(o.quotes || {}).length ? o.quotes : { XAUUSD: null, XAGUSD: null };
    $("#tickers").innerHTML = Object.entries(syms).map(([s, q]) => `
      <div class="tick"><span class="sym">${s}</span><span class="px">${q ? px(q.bid, s) : "—"}</span>
      <span class="kv">SPRD <b>${q ? (q.ask - q.bid).toFixed(DIG[s] ?? 2) : "—"}</b></span><span class="kv">live quote</span></div>`).join("");
    const msg = `Downloading price history: ${pr.done} / ${pr.total} days (${pr.pct}%).<br><span class="dim">Free source, throttled — about 15–30 min on a fresh server. Live prices are already flowing; the chart, matrix and signals appear by themselves when it's done.</span>`;
    $("#matrix").innerHTML = `<div class="pad">${msg}<div class="bar" style="margin-top:10px"><i style="width:${pr.pct}%;left:0;background:var(--amber)"></i></div></div>`;
    $("#chartmsg").innerHTML = `<div><b>Preparing chart…</b><br>${pr.pct}% of history downloaded</div>`;
    $("#chartmsg").hidden = false;
    renderSession(o); tickClock(o.now);
  }

  // ------------------------------------------------------------ live mode
  async function refreshLive() {
    try {
      const [f, o, sg, g, w] = await Promise.all([api("/api/feed"), api("/api/overview"), api("/api/signals?limit=500"), api("/api/guard"), api("/api/watch")]);
      const newWatch = (w.watch || []).filter(x => !(st.watch || []).some(y => y.key === x.key));
      for (const x of newWatch) log(`GET READY · ${x.dir === 1 ? "BUY" : "SELL"} ${x.symbol} setup forming · trigger ${x.dir === 1 ? "above" : "below"} ${px(x.trigger, x.symbol)}`, "");
      st.watch = w.watch || [];
      renderGuard(g);
      if (o.warming) { renderWarming(o); st.signals = sg.signals; renderFeed(); return; }
      if (!st.ready) { st.ready = await loadFull(); if (st.ready) log("price history ready — dashboard live", "up"); return; }
      const st0 = f.status || {};
      const age = st0.last_quote ? Math.round(Date.now() / 1000 - st0.last_quote) : null;
      $("#mode").textContent = `LIVE · ${st0.feed || "—"}${age != null && age > 30 ? ` · ${age}s old` : ""}`;
      $("#mode").style.borderColor = $("#mode").style.color = (age != null && age <= 30) ? css("--green") : css("--red");
      for (const [sym, q] of Object.entries(f.quotes || {})) {
        if (o.symbols[sym]) { o.symbols[sym].price = q.bid; o.symbols[sym].spread = +(q.ask - q.bid).toFixed(3); }
      }
      st.overview = o; renderTickers(o); renderMatrix(o); renderSession(o);
      const before = new Set(st.signals.filter(x => x.source === "live").map(x => x.id + x.state));
      st.signals = sg.signals;
      for (const x of st.signals.filter(x => x.source === "live" && !before.has(x.id + x.state)))
        if (before.size) log(`${x.id} · ${x.dir === 1 ? "BUY" : "SELL"} ${x.symbol} · ${STATE[x.state] || x.state}`, x.r < 0 ? "dn" : "up");
      renderFeed();
      if (!f.ready || !Object.values(f.ready).every(Boolean)) $("#feedcount").textContent += " · warming up";
    } catch (e) { log(esc(e.message), "dn"); }
  }
  const GUARD = { ACTIVE: ["ACTIVE", "--green"], HALF: ["HALF SIZE", "--amber"], DAY_STOP: ["DAY STOP", "--amber"], PAUSED: ["PAUSED", "--red"] };
  function renderGuard(g) {
    const el = $("#guard"), btn = $("#guardbtn");
    const [label, color] = GUARD[g.state] || [g.state, "--dim"];
    el.hidden = false;
    el.textContent = `${label} · ${g.equity_r >= 0 ? "+" : ""}${g.equity_r}R · DD ${g.drawdown_r}R`;
    el.style.color = el.style.borderColor = css(color);
    el.title = (g.reasons || []).join("\n") || `trades ${g.trades} · avg ${g.avg_r}R · today ${g.today_r}R`;
    btn.hidden = g.state !== "PAUSED";
    if (st.guardState && st.guardState !== g.state) log(`guard: ${label}${g.reasons && g.reasons.length ? " — " + esc(g.reasons[0]) : ""}`, g.state === "ACTIVE" ? "up" : "dn");
    st.guardState = g.state;
  }
  async function guardResume() {
    if (!confirm("Resume signals? Drawdown and edge tracking restart from now.")) return;
    const r = await fetch("/api/guard/resume", { method: "POST", credentials: "same-origin" });
    if (r.ok) renderGuard(await r.json());
  }
  function startLive() {
    $("#guardbtn").onclick = guardResume;
    setInterval(() => tickClock(Math.floor(Date.now() / 1000)), 1000);
    setInterval(refreshLive, 5000);
    setInterval(pollTicks, 2000);                                   // live candle + header price every 2 s
    setInterval(() => { if (st.liveChart) loadChart(); }, 120000);   // periodic full re-sync
    refreshLive();
  }

  // ------------------------------------------------------------ alerts: bell, toasts, sound, device notifications
  const AL = { list: [], maxId: 0, seen: 0, ready: false };
  try { AL.seen = +(localStorage.getItem("xahoo-seen") || 0); } catch (e) { /* storage unavailable */ }
  let audio;
  function beep(kind) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const tones = kind === "signal" ? [880, 1175, 1568] : kind === "prealert" ? [660, 880] : [520];
      tones.forEach((f, i) => {
        const o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = f; o.type = "sine"; o.connect(g); g.connect(audio.destination);
        const t = audio.currentTime + i * 0.16;
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
        o.start(t); o.stop(t + 0.15);
      });
    } catch (e) { /* audio blocked until first click */ }
  }
  function toast(a) {
    const sticky = a.kind === "signal" || a.kind === "prealert";
    const el = document.createElement("div");
    el.className = `toast lv-${a.level}${sticky ? " sticky" : ""}`;
    el.innerHTML = `<button class="x" title="Close" aria-label="Close">✕</button><b>${esc(a.title)}</b><span>${esc(a.body)}</span><div class="tt">${tIST(a.ts)} IST</div>`;
    el.querySelector(".x").onclick = e => { e.stopPropagation(); el.remove(); };
    el.onclick = () => openBell();
    $("#toasts").prepend(el);
    if (!sticky) setTimeout(() => el.remove(), 10000);
    // keep at most 5 on screen: drop the oldest non-sticky first
    while ($("#toasts").children.length > 5) {
      const old = [...$("#toasts").children].reverse().find(t => !t.classList.contains("sticky")) || $("#toasts").lastChild;
      old.remove();
    }
  }
  function renderBell() {
    const unread = AL.list.filter(a => a.id > AL.seen).length;
    $("#bellcount").hidden = !unread;
    $("#bellcount").textContent = unread > 99 ? "99+" : unread;
    $("#belllist").innerHTML = AL.list.length ? AL.list.slice(0, 60).map(a => `
      <div class="alert lv-${a.level} ${a.id > AL.seen ? "unread" : ""}">
        <i class="abar"></i><span class="at">${esc(a.title)}</span><span class="tm">${tIST(a.ts)}</span>
        <span class="ab">${esc(a.body)}</span>
      </div>`).join("") : `<div class="pad dim">No alerts yet.</div>`;
  }
  function markRead() {
    AL.seen = AL.maxId;
    try { localStorage.setItem("xahoo-seen", String(AL.seen)); } catch (e) { /* ignore */ }
    renderBell();
  }
  function openBell() { $("#bellpanel").hidden = false; renderBell(); }
  async function pollAlerts() {
    try {
      const r = await api(`/api/alerts?since=${AL.maxId}&limit=100`);
      const fresh = (r.alerts || []).sort((a, b) => a.id - b.id);
      if (!fresh.length) { AL.ready = true; return; }
      AL.maxId = Math.max(AL.maxId, ...fresh.map(a => a.id));
      AL.list = [...fresh].reverse().concat(AL.list).slice(0, 200);
      if (AL.ready) {
        for (const a of fresh.slice(-5)) {                // oldest first, so the newest ends up on top
          toast(a);
          log(`${esc(a.title)} · ${esc(a.body)}`, a.level === "bad" ? "dn" : a.level === "good" ? "up" : "");
          if (document.hidden && !st.pushOn && typeof Notification !== "undefined" && Notification.permission === "granted" && navigator.serviceWorker) {
            navigator.serviceWorker.ready.then(reg => reg.showNotification(a.title, { body: a.body, tag: "xahoo-" + a.id, icon: "/icons/icon-192.png" }));
          }
        }
        beep((fresh.find(a => a.kind === "signal") || fresh[fresh.length - 1]).kind);
        $("#bell").classList.remove("ring"); void $("#bell").offsetWidth; $("#bell").classList.add("ring");
      }
      AL.ready = true;
      renderBell();
    } catch (e) { /* offline / login: next poll */ }
  }

  // ------------------------------------------------------------ device push (works with the app closed)
  const b64u = s => { const p = "=".repeat((4 - s.length % 4) % 4); const b = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(b, c => c.charCodeAt(0)); };
  async function pushState() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || typeof Notification === "undefined") { $("#notif").title = "Notifications not supported here (iPhone: install to home screen first)"; return; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    st.pushOn = !!sub && Notification.permission === "granted";
    $("#notif").textContent = st.pushOn ? "🔔 ON" : "🔕";
    $("#notif").title = st.pushOn ? "Device notifications on — tap to send a test" : "Turn on device notifications";
  }
  async function enablePush() {
    try {
      if (typeof Notification === "undefined" || !("PushManager" in window)) { $("#installhelp").hidden = false; return; }
      if (st.pushOn) { await fetch("/api/push/test", { method: "POST", credentials: "same-origin" }); return; }
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { log("notifications blocked in browser settings", "dn"); return; }
      const { key } = await api("/api/push/key");
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64u(key) });
      const r = await fetch("/api/push/subscribe", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(sub.toJSON()) });
      if (!r.ok) throw new Error("subscribe failed " + r.status);
      await fetch("/api/push/test", { method: "POST", credentials: "same-origin" });
      log("device notifications on — a test alert was sent", "up");
    } catch (e) { log("notifications: " + esc(e.message || e), "dn"); }
    pushState();
  }

  // ------------------------------------------------------------ install as app (desktop + mobile)
  let deferredInstall = null;
  const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  function initInstall() {
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferredInstall = e; $("#install").hidden = false; });
    window.addEventListener("appinstalled", () => { $("#install").hidden = true; log("XAHOO installed as an app", "up"); });
    if (!standalone() && ios) $("#install").hidden = false;
    $("#install").onclick = async () => {
      if (deferredInstall) { deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; $("#install").hidden = true; }
      else $("#installhelp").hidden = false;
    };
    $("#installclose").onclick = () => { $("#installhelp").hidden = true; };
  }

  function initAlerts() {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").then(pushState).catch(() => {});
    initInstall();
    $("#bell").onclick = e => { e.stopPropagation(); $("#bellpanel").hidden ? openBell() : ($("#bellpanel").hidden = true); };
    $("#bellpanel").onclick = e => e.stopPropagation();
    document.addEventListener("click", () => { if (!$("#bellpanel").hidden) { $("#bellpanel").hidden = true; markRead(); } });
    $("#markread").onclick = markRead;
    $("#notif").onclick = enablePush;
    $("#logout").onclick = async () => { await fetch("/api/logout", { method: "POST", credentials: "same-origin" }); location.replace("/login"); };
    document.addEventListener("click", () => { if (!audio) beep("none"); }, { once: true });   // unlock audio
    pollAlerts();
    setInterval(pollAlerts, 5000);
  }

  async function loadFull() {
    const [o, sg, s, p] = await Promise.all([api("/api/overview"), api("/api/signals?limit=2000"), api("/api/stats"), api("/api/params")]);
    st.signals = sg.signals; st.stats = s;
    $("#params").textContent = JSON.stringify(p.params, null, 2);
    $("#pver").textContent = "version " + p.version;
    if (o.warming) { renderWarming(o); renderFeed(); return false; }
    st.overview = o;
    renderTickers(o); renderMatrix(o); renderSession(o); tickClock(o.now);
    $("#kpis").innerHTML = kpiHtml(s.summary);
    $("#perfwin").textContent = `last ${s.window_days || "?"} days · net of spread`;
    renderFeed();
    await loadChart();
    $("#chartmsg").hidden = true;
    log(`${st.signals.length} signals loaded · net ${s.summary.total_r ?? 0}R over the replay window`);
    return true;
  }

  async function boot() {
    initTheme(); bind(); initChart(); calc(); initAlerts();
    try {
      const h = await api("/api/health");
      $("#mode").textContent = h.mode;
      $("#devwarn").hidden = h.auth;
      log(`connected · mode ${h.mode} · params ${h.params_version}`);
      if (h.mode === "REPLAY") log("REPLAY: engine runs over cached history; prices are not live.", "dn");
      if (h.mode === "LIVE") startLive();                 // live prices & alerts even while history downloads
      st.ready = await loadFull();
      if (!st.ready) log("downloading price history — the dashboard fills in by itself when it's ready");
    } catch (e) {
      log(esc(e.message), "dn");
    }
  }
  boot();
})();
