/* XAHOO terminal UI — vanilla JS, no build step. */
(() => {
  "use strict";
  const IST = 19800;                         // seconds; chart axis is shown in IST
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const st = { sym: "XAUUSD", tf: "5m", signals: [], selected: null, overview: null, stats: null };
  const DIG = { XAUUSD: 2, XAGUSD: 3 };
  const CONTRACT = { XAUUSD: 100, XAGUSD: 5000 };
  const SETUP = { ema12_pullback: "EMA12 pullback", ema200_retest: "EMA200 retest", range: "Range edge", sweep: "Liq. sweep" };
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
    if (r.status === 401) { await login(); return api(path); }
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }
  async function login() {
    const pw = prompt("XAHOO admin password");
    if (pw == null) throw new Error("login cancelled");
    const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: pw }) });
    if (!r.ok) { alert("Wrong password"); return login(); }
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
    $("#feed").innerHTML = list.map(s => `
      <div class="sig ${st.selected && st.selected.id === s.id ? "sel" : ""}" data-id="${esc(s.id)}">
        <span class="side ${s.dir === 1 ? "up" : "dn"}">${s.dir === 1 ? "BUY" : "SELL"}</span>
        <span>${s.symbol.slice(0, 3)} · ${s.tf} · ${srcTag(s)}</span>
        <span class="res">${resTxt(s)}</span>
        <span class="meta">${tIST(s.close_time)} · ${SETUP[s.setup] || s.setup} · @ ${px(s.entry, s.symbol)}</span>
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
    $("#d-close").onclick = () => { $("#drawer").hidden = true; };
    ["#f-sym", "#f-tf", "#f-grade", "#f-res"].forEach(s => $(s).onchange = renderTable);
    $("#csv").onclick = exportCsv;
    ["#acc", "#riskpct", "#sldist", "#calcsym"].forEach(s => $(s).oninput = calc);
    document.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#cmdk").hidden = false; $("#cmdin").value = ""; $("#cmdin").focus(); }
      else if (e.key === "Escape") { $("#cmdk").hidden = true; $("#drawer").hidden = true; }
      else if (/^F[1-4]$/.test(e.key)) { e.preventDefault(); showView(["terminal", "signals", "analytics", "settings"][+e.key[1] - 1]); }
    });
    $("#cmdin").addEventListener("keydown", e => { if (e.key === "Enter") { runCmd(e.target.value); $("#cmdk").hidden = true; } });
    $("#cmdk").onclick = e => { if (e.target.id === "cmdk") $("#cmdk").hidden = true; };
  }

  function tickClock(now) {
    $("#clock").textContent = tIST(now, false) + " IST";
  }

  // ------------------------------------------------------------ live mode
  async function refreshLive() {
    try {
      const [f, o, sg] = await Promise.all([api("/api/feed"), api("/api/overview"), api("/api/signals?limit=500")]);
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
  function startLive() {
    setInterval(() => tickClock(Math.floor(Date.now() / 1000)), 1000);
    setInterval(refreshLive, 5000);
    setInterval(() => { if (!st.selected) loadChart(); }, 30000);
    refreshLive();
  }

  async function boot() {
    initTheme(); bind(); initChart(); calc();
    try {
      const h = await api("/api/health");
      $("#mode").textContent = h.mode;
      $("#devwarn").hidden = h.auth;
      log(`connected · mode ${h.mode} · params ${h.params_version} · ${Object.entries(h.bars).map(([s, n]) => `${s} ${n.toLocaleString()} bars`).join(" · ")}`);
      if (h.mode === "REPLAY") log("REPLAY: engine runs over cached history; prices are not live.", "dn");
      const [o, sg, s, p] = await Promise.all([api("/api/overview"), api("/api/signals?limit=2000"), api("/api/stats"), api("/api/params")]);
      st.overview = o; st.signals = sg.signals; st.stats = s;
      renderTickers(o); renderMatrix(o); renderSession(o); tickClock(o.now);
      $("#kpis").innerHTML = kpiHtml(s.summary);
      $("#perfwin").textContent = `last ${s.window_days || "?"} days · net of spread`;
      $("#params").textContent = JSON.stringify(p.params, null, 2);
      $("#pver").textContent = "version " + p.version;
      renderFeed();
      await loadChart();
      log(`${st.signals.length} signals loaded · TP1 hit ${s.summary.tp1_hit_rate ?? "–"}% · net ${s.summary.total_r ?? 0}R`);
      if (h.mode === "LIVE") startLive();
    } catch (e) {
      log(esc(e.message), "dn");
    }
  }
  boot();
})();
