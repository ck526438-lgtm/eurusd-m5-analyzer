/* EURUSD M5 — Espace d'analyse */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const C = {
    up: css("--up"), down: css("--down"), accent: css("--accent"), muted: css("--muted"),
    line: css("--line"), text: css("--text"), warn: css("--warn"), panel: css("--panel"),
    emaF: "#f2b84b", emaM: "#4c8dff", emaS: "#b07cff",
  };
  const f5 = (v) => (v == null ? "—" : Number(v).toFixed(5));
  const sgn = (v, d = 1) => (v > 0 ? "+" : "") + Number(v).toFixed(d);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso, withDay = true) => {
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, "0");
    const t = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
    return withDay ? `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)} ${t}` : t;
  };

  const store = {
    get(k, d) { try { const v = localStorage.getItem("eurusd." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("eurusd." + k, JSON.stringify(v)); } catch { /* indisponible */ } },
  };

  const S = {
    snap: null, settings: null, meta: null, journal: [], view: "analyse",
    selected: null, fitted: false,
    prefs: { browser: store.get("browser", false), sound: store.get("sound", true) },
  };

  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch { /* corps vide */ }
      throw new Error(msg);
    }
    return r.json();
  }

  /* ------------------------------------------------------------------ navigation */
  function show(view) {
    S.view = view;
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
    if (view === "signaux") loadJournal();
    if (view === "reglages") fillSettings();
    if (view === "analyse") requestAnimationFrame(resizeCharts);
  }
  $$(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.view)));
  $$("[data-goto]").forEach((b) => b.addEventListener("click", () => show(b.dataset.goto)));

  /* ------------------------------------------------------------------ graphiques */
  const LWC = window.LightweightCharts;
  const baseOpts = {
    layout: { background: { color: "transparent" }, textColor: C.muted, fontFamily: "JetBrains Mono, monospace", fontSize: 11 },
    grid: { vertLines: { color: "rgba(34,41,54,.55)" }, horzLines: { color: "rgba(34,41,54,.55)" } },
    rightPriceScale: { borderColor: C.line },
    timeScale: { borderColor: C.line, timeVisible: true, secondsVisible: false, rightOffset: 8 },
    crosshair: { mode: LWC.CrosshairMode.Normal },
    localization: { locale: "fr-FR", priceFormatter: (p) => p.toFixed(5) },
  };
  const chart = LWC.createChart($("#chart"), { ...baseOpts, autoSize: true });
  const candles = chart.addCandlestickSeries({
    upColor: C.up, downColor: C.down, borderUpColor: C.up, borderDownColor: C.down,
    wickUpColor: C.up, wickDownColor: C.down, priceFormat: { type: "price", precision: 5, minMove: 0.00001 },
  });
  const ema = {
    fast: chart.addLineSeries({ color: C.emaF, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
    mid: chart.addLineSeries({ color: C.emaM, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
    slow: chart.addLineSeries({ color: C.emaS, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
  };
  const rsiChart = LWC.createChart($("#rsi-chart"), {
    ...baseOpts, autoSize: true,
    timeScale: { ...baseOpts.timeScale, visible: false },
    localization: { locale: "fr-FR", priceFormatter: (p) => p.toFixed(0) },
    rightPriceScale: { borderColor: C.line, scaleMargins: { top: 0.1, bottom: 0.1 } },
  });
  const rsi = rsiChart.addLineSeries({ color: C.accent, lineWidth: 1.5, priceLineVisible: false });
  [70, 30].forEach((v) => rsi.createPriceLine({ price: v, color: "rgba(138,147,163,.45)", lineStyle: 2, lineWidth: 1, axisLabelVisible: false }));
  rsi.createPriceLine({ price: 50, color: "rgba(138,147,163,.18)", lineStyle: 1, lineWidth: 1, axisLabelVisible: false });

  let syncing = false;
  const sync = (src, dst) => src.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (syncing || !r) return;
    syncing = true; dst.timeScale().setVisibleLogicalRange(r); syncing = false;
  });
  sync(chart, rsiChart); sync(rsiChart, chart);

  function resizeCharts() { /* autoSize gère le redimensionnement */ }

  let zoneLines = [], levelLines = [];
  function drawZones() {
    zoneLines.forEach((l) => candles.removePriceLine(l));
    zoneLines = [];
    if (!$("#t-zones").checked || !S.snap) return;
    for (const z of S.snap.zones) {
      zoneLines.push(candles.createPriceLine({
        price: z.price, lineStyle: 2, lineWidth: z.touches >= 2 ? 2 : 1, axisLabelVisible: false,
        color: z.kind === "support" ? "rgba(34,195,154,.35)" : "rgba(240,86,106,.35)",
      }));
    }
  }
  function drawLevels(sig) {
    levelLines.forEach((l) => candles.removePriceLine(l));
    levelLines = [];
    if (!sig) return;
    const L = [["Entrée", sig.entry, C.text, 0], ["SL", sig.sl, C.down, 2], ["TP1", sig.tp1, C.up, 2]];
    if (Math.abs(sig.tp2 - sig.tp1) > 1e-6) L.push(["TP2", sig.tp2, C.up, 2]);
    for (const [title, price, color, style] of L)
      levelLines.push(candles.createPriceLine({ price, color, lineStyle: style, lineWidth: 1, title, axisLabelVisible: true }));
  }
  function drawMarkers() {
    const m = !$("#t-sig").checked || !S.snap ? [] : S.snap.chart.markers.map((k) => ({
      time: k.time, position: k.direction === 1 ? "belowBar" : "aboveBar",
      color: k.direction === 1 ? C.up : C.down, shape: k.direction === 1 ? "arrowUp" : "arrowDown",
      text: k.quality, size: 1.1,
    }));
    candles.setMarkers(m);
  }
  $("#t-zones").addEventListener("change", drawZones);
  $("#t-sig").addEventListener("change", drawMarkers);
  $("#t-ema").addEventListener("change", (e) => Object.values(ema).forEach((s) => s.applyOptions({ visible: e.target.checked })));
  $("#fit-btn").addEventListener("click", () => { focusLatest(); });

  function focusLatest() {
    const n = S.snap?.chart.candles.length || 0;
    chart.timeScale().setVisibleLogicalRange({ from: n - 140, to: n + 8 });
  }
  function focusTime(isoClose) {
    const t = Math.floor(new Date(isoClose).getTime() / 1000) - 300;
    const arr = S.snap?.chart.candles || [];
    const i = arr.findIndex((c) => c.time >= t);
    if (i < 0) { toast("Signal hors de la fenêtre affichée", "Il est plus ancien que les 600 dernières bougies.", "err"); return false; }
    chart.timeScale().setVisibleLogicalRange({ from: i - 70, to: i + 70 });
    return true;
  }

  chart.subscribeCrosshairMove((p) => {
    const bar = p && p.time ? p.seriesData.get(candles) : null;
    renderLegend(bar);
  });
  chart.subscribeClick((p) => {
    if (!p || !p.time || !S.snap) return;
    const mk = S.snap.chart.markers.find((m) => m.time === p.time);
    if (!mk) return;
    const sig = S.journal.find((j) => j.key === mk.key) || null;
    if (sig) selectSignal(sig, false);
  });

  function renderLegend(bar) {
    const s = S.snap;
    if (!s) return;
    const last = s.chart.candles[s.chart.candles.length - 1];
    const b = bar || last;
    const e = (arr) => { const v = arr.find((x) => x.time === b.time); return v ? v.value.toFixed(5) : "—"; };
    $("#legend").innerHTML = `
      <span>O <span class="mono">${f5(b.open)}</span></span><span>H <span class="mono">${f5(b.high)}</span></span>
      <span>L <span class="mono">${f5(b.low)}</span></span><span>C <span class="mono ${b.close >= b.open ? "up" : "down"}">${f5(b.close)}</span></span>
      <span><i style="background:${C.emaF}"></i>EMA 20 <span class="mono">${e(s.chart.ema_fast)}</span></span>
      <span><i style="background:${C.emaM}"></i>EMA 50 <span class="mono">${e(s.chart.ema_mid)}</span></span>
      <span><i style="background:${C.emaS}"></i>EMA 200 <span class="mono">${e(s.chart.ema_slow)}</span></span>`;
  }

  /* ------------------------------------------------------------------ état */
  async function loadState() {
    try {
      const s = await api("/api/state");
      if (!s.ready) {
        setFeed("err", s.error ? "Données indisponibles" : "Chargement…");
        if (s.error) banner(s.error);
        return;
      }
      S.snap = s;
      banner(null);
      render();
    } catch (e) {
      setFeed("err", "Serveur injoignable");
    }
  }

  function render() {
    const s = S.snap;
    setFeed(s.source === "demo" ? "demo" : "live", s.source_label);
    $("#price").textContent = f5(s.price);
    const ch = s.change_24h_pips;
    $("#chg").innerHTML = ch == null ? "" : `<span class="${ch >= 0 ? "up" : "down"}">${sgn(ch)} pips · 24 h</span>`;
    $("#day-high").textContent = f5(s.context.day_high);
    $("#day-low").textContent = f5(s.context.day_low);
    $("#atr").textContent = s.context.atr_pips.toFixed(1) + " pips";
    $("#last-close").textContent = fmtDate(s.last_close) + " UTC";
    document.title = `${f5(s.price)} · EURUSD M5`;

    candles.setData(s.chart.candles);
    ema.fast.setData(s.chart.ema_fast);
    ema.mid.setData(s.chart.ema_mid);
    ema.slow.setData(s.chart.ema_slow);
    rsi.setData(s.chart.rsi);
    const lastRsi = s.chart.rsi[s.chart.rsi.length - 1];
    $("#rsi-val").textContent = lastRsi ? lastRsi.value.toFixed(1) : "";
    drawMarkers(); drawZones();
    if (!S.fitted) { focusLatest(); S.fitted = true; }
    renderLegend();

    const showSig = S.selected || (s.radar && !s.radar.blocked ? s.radar : null);
    drawLevels(showSig);
    renderRadar(); renderContext(); renderZones(); renderRecent();
    const open = s.journal_stats.open;
    $("#open-count").hidden = !open;
    $("#open-count").textContent = open;
  }

  function gauge(score, min, dir) {
    const r = 31, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(1, score / 10));
    const col = score >= min ? (dir === 1 ? C.up : C.down) : C.muted;
    const minA = (min / 10) * c;
    return `<div class="gauge"><svg width="74" height="74" viewBox="0 0 74 74">
      <circle cx="37" cy="37" r="${r}" fill="none" stroke="${C.line}" stroke-width="6"/>
      <circle cx="37" cy="37" r="${r}" fill="none" stroke="${col}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${pct * c} ${c}"/>
      <circle cx="37" cy="37" r="${r}" fill="none" stroke="${C.warn}" stroke-width="8" stroke-dasharray="1.5 ${c}" stroke-dashoffset="${-minA}"/>
      </svg><div class="val"><div>${score.toFixed(1)}<small>/ 10</small></div></div></div>`;
  }

  function sigBlock(sig, title) {
    const buy = sig.direction === 1;
    const valid = !sig.blocked;
    const facts = sig.factors.map((f) => `<li class="${f.tone}"><span class="ic">${f.points > 0 ? "✓" : f.points < 0 ? "✕" : "·"}</span>
        <span>${esc(f.label)}</span><span class="pts">${f.points ? sgn(f.points, f.points % 1 ? 1 : 0) : "0"}</span></li>`).join("");
    return `
      <div class="radar-top">
        ${gauge(sig.score, S.snap.min_score, sig.direction)}
        <div>
          <span class="side-badge ${buy ? "buy" : "sell"}">${buy ? "▲ ACHAT" : "▼ VENTE"}</span>
          <span class="q-badge q-${sig.quality}">${sig.quality}</span>
          <div class="radar-title">${esc(sig.pattern)}</div>
          <div class="muted sm">${title}</div>
        </div>
      </div>
      <div class="verdict ${valid ? "ok" : "no"} ${buy ? "" : "sell"}">${valid ? "Signal validé — toutes les conditions sont réunies" : "Pas de signal : " + esc(sig.blocked)}</div>
      <div class="levels">
        <div><span class="label">Entrée</span><b>${f5(sig.entry)}</b></div>
        <div><span class="label">Stop</span><b class="down">${f5(sig.sl)}</b><span class="sub">${sig.risk_pips} p</span></div>
        <div><span class="label">TP1</span><b class="up">${f5(sig.tp1)}</b><span class="sub">1:${sig.rr1}</span></div>
        <div><span class="label">TP2</span><b class="up">${f5(sig.tp2)}</b><span class="sub">1:${sig.rr2}</span></div>
      </div>
      <ul class="factors">${facts}</ul>`;
  }

  function renderRadar() {
    const s = S.snap, body = $("#radar-body");
    if (S.selected) {
      const j = S.selected;
      $("#radar-time").innerHTML = `<button class="link" id="unselect">← Revenir au direct</button>`;
      body.innerHTML = sigBlock({ ...j, blocked: null, rr1: rr(j, j.tp1), rr2: rr(j, j.tp2) }, `Signal du ${fmtDate(j.time)} UTC · ${statusLabel(j.status)}`);
      $("#unselect").onclick = () => { S.selected = null; render(); focusLatest(); };
      return;
    }
    $("#radar-time").textContent = "bougie de " + fmtDate(s.last_close, false) + " UTC";
    if (s.radar) {
      body.innerHTML = sigBlock(s.radar, "Analyse de la dernière bougie clôturée");
    } else {
      const prev = s.radar_recent;
      body.innerHTML = `<div class="radar-empty"><b>Aucune figure sur la dernière bougie</b>Le système attend une figure de chandelier exploitable.</div>
        ${prev ? `<div class="radar-prev">Dernier setup repéré à ${fmtDate(prev.close_time, false)} : <b>${prev.side} ${esc(prev.pattern)}</b> — ${prev.score}/10${prev.blocked ? " (" + esc(prev.blocked) + ")" : " ✓ validé"}</div>` : ""}`;
    }
  }
  const rr = (j, t) => (Math.abs(t - j.entry) / Math.max(Math.abs(j.entry - j.sl), 1e-9)).toFixed(2);

  function renderContext() {
    const c = S.snap.context;
    const trend = (v) => v === 1 ? `<b class="up">▲ Haussière</b>` : v === -1 ? `<b class="down">▼ Baissière</b>` : `<b class="muted">↔ Neutre</b>`;
    const rsiTxt = c.rsi >= 70 ? "Suracheté" : c.rsi <= 30 ? "Survendu" : c.rsi >= 55 ? "Acheteurs" : c.rsi <= 45 ? "Vendeurs" : "Équilibre";
    const adxTxt = c.adx >= 25 ? "Tendance forte" : c.adx >= 18 ? "Directionnel" : "Sans direction";
    const sess = c.sessions.map(([a, b]) => `${a}h–${b}h`).join(" · ");
    $("#ctx").innerHTML = `
      <div class="ctx"><span class="label">Tendance H1</span>${trend(c.h1_bias)}</div>
      <div class="ctx"><span class="label">Tendance M5</span>${trend(c.m5_trend)}</div>
      <div class="ctx"><span class="label">RSI 14</span><b>${c.rsi.toFixed(0)} · <span class="muted">${rsiTxt}</span></b><div class="bar"><i style="width:${c.rsi}%;background:${c.rsi >= 70 ? C.down : c.rsi <= 30 ? C.up : C.accent}"></i></div></div>
      <div class="ctx"><span class="label">ADX 14</span><b>${c.adx.toFixed(0)} · <span class="muted">${adxTxt}</span></b><div class="bar"><i style="width:${Math.min(100, c.adx * 2)}%;background:${c.adx >= 18 ? C.accent : C.muted}"></i></div></div>
      <div class="ctx"><span class="label">Volatilité (ATR)</span><b>${c.atr_pips.toFixed(1)} pips</b></div>
      <div class="ctx"><span class="label">Session</span><b class="${c.in_session ? "up" : "muted"}">${c.in_session ? "● Active" : "○ Fermée"}</b><span class="muted sm">${sess} UTC</span></div>`;
  }

  function renderZones() {
    const s = S.snap;
    const zs = [...s.zones].sort((a, b) => b.price - a.price);
    let html = "", placed = false;
    for (const z of zs) {
      if (!placed && z.price < s.price) { html += `<div class="zone now">prix ${f5(s.price)}</div>`; placed = true; }
      const dots = [1, 2, 3, 4].map((k) => `<i class="${z.touches >= k ? "on" : ""}"></i>`).join("");
      html += `<div class="zone"><span class="k ${z.kind}">${z.kind === "support" ? "Support" : "Résistance"}</span>
        <span class="dots" title="${z.touches} touche(s)">${dots}</span><span class="mono">${f5(z.price)}</span>
        <span class="d mono">${sgn(z.distance_pips)}</span></div>`;
    }
    if (!placed) html += `<div class="zone now">prix ${f5(s.price)}</div>`;
    $("#zones").innerHTML = zs.length ? html : `<div class="muted sm">Pas encore assez de pivots.</div>`;
  }

  const statusLabel = (st) => ({ "en cours": "En cours", TP2: "TP2 atteint", BE: "TP1 + BE", SL: "Stop", temps: "Clôturé (temps)" }[st] || st);
  const statusPill = (st) => `<span class="status st-${st.replace(" ", "")}">${statusLabel(st)}</span>`;
  const rCell = (j) => j.status === "en cours" ? `<span class="muted">${sgn(j.result_r, 2)} R</span>` : `<span class="${j.result_r > 0 ? "up" : j.result_r < 0 ? "down" : "muted"}">${sgn(j.result_r, 2)} R</span>`;

  function renderRecent() {
    const rec = S.snap.recent;
    if (!rec.length) { $("#recent").innerHTML = `<div class="muted sm">Aucun signal pour l'instant.</div>`; return; }
    $("#recent").innerHTML = rec.map((j, k) => `<div class="rec" data-k="${k}">
      <span class="t">${fmtDate(j.time)}</span>
      <span><b class="${j.direction === 1 ? "up" : "down"}">${j.direction === 1 ? "▲" : "▼"}</b> ${esc(j.pattern)} <span class="q-badge q-${j.quality}">${j.quality}</span></span>
      ${statusPill(j.status)}</div>`).join("");
    $$(".rec").forEach((el) => el.addEventListener("click", () => selectSignal(rec[+el.dataset.k])));
  }

  function selectSignal(j, move = true) {
    S.selected = j;
    show("analyse");
    render();
    if (move) focusTime(j.time);
  }

  /* ------------------------------------------------------------------ journal */
  const F = { side: "", status: "", quality: "" };
  async function loadJournal() {
    try {
      const d = await api("/api/journal");
      S.journal = d.signals;
      renderJournalKpis(d.stats);
      renderJournal();
    } catch (e) { toast("Journal indisponible", e.message, "err"); }
  }
  function renderJournalKpis(st) {
    const k = (label, val, hint, cls = "") => `<div class="kpi"><span class="label">${label}</span><b class="${cls}">${val}</b>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
    $("#journal-kpis").innerHTML = st.closed
      ? k("Signaux clôturés", st.closed, `${st.open} en cours`) +
        k("Réussite", st.win_rate + " %", "trades > 0 R") +
        k("Résultat total", sgn(st.total_r, 2) + " R", "", st.total_r >= 0 ? "up" : "down") +
        k("Espérance", sgn(st.expectancy_r, 2) + " R", "par signal") +
        k("Profit factor", st.profit_factor ?? "—", "gains / pertes")
      : k("Signaux clôturés", 0, `${st.open} en cours`) + k("Statistiques", "—", "disponibles après les premiers résultats");
  }
  function renderJournal() {
    const rows = S.journal.filter((j) => (!F.side || j.side === F.side) && (!F.status || j.status === F.status) && (!F.quality || j.quality === F.quality));
    $("#journal-empty").hidden = rows.length > 0;
    $("#journal-table tbody").innerHTML = rows.map((j, k) => `
      <tr class="row" data-k="${k}">
        <td class="mono">${fmtDate(j.time)}</td>
        <td><span class="side-badge ${j.direction === 1 ? "buy" : "sell"}">${j.direction === 1 ? "▲ ACHAT" : "▼ VENTE"}</span></td>
        <td>${esc(j.pattern)} ${j.origin === "historique" ? `<span class="muted sm" title="Détecté au démarrage sur l'historique">· hist.</span>` : ""}</td>
        <td><span class="q-badge q-${j.quality}">${j.quality}</span> <span class="mono muted">${j.score}</span></td>
        <td class="r">${f5(j.entry)}</td><td class="r down">${f5(j.sl)}</td><td class="r up">${f5(j.tp1)}</td><td class="r up">${f5(j.tp2)}</td>
        <td>${statusPill(j.status)}</td><td class="r">${rCell(j)}</td>
      </tr>`).join("");
    $$("#journal-table tr.row").forEach((tr) => tr.addEventListener("click", () => toggleDetail(tr, rows[+tr.dataset.k])));
  }
  function toggleDetail(tr, j) {
    const next = tr.nextElementSibling;
    if (next && next.classList.contains("detail")) { next.remove(); return; }
    const d = document.createElement("tr");
    d.className = "detail";
    d.innerHTML = `<td colspan="10"><div class="detail-grid">
      <div><h3 style="margin-bottom:8px">Pourquoi ce signal</h3><ul class="factors">${j.factors.map((f) => `<li class="${f.tone}"><span class="ic">${f.points > 0 ? "✓" : f.points < 0 ? "✕" : "·"}</span><span>${esc(f.label)}</span><span class="pts">${sgn(f.points, f.points % 1 ? 1 : 0)}</span></li>`).join("")}</ul></div>
      <div><h3 style="margin-bottom:8px">Note personnelle</h3><textarea placeholder="Pris ? Pas pris ? Ce que tu as observé…">${esc(j.note)}</textarea>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn sm primary" data-a="save">Enregistrer la note</button><button class="btn sm ghost" data-a="chart">Voir sur le graphique</button></div>
      <div class="muted sm" style="margin-top:8px">${j.exit_time ? "Sortie : " + fmtDate(j.exit_time) + " UTC · " : ""}Risque ${j.risk_pips} pips</div></div></div></td>`;
    tr.after(d);
    $("[data-a=save]", d).onclick = async () => {
      await api(`/api/journal/${j.key}/note`, { method: "PUT", body: JSON.stringify({ note: $("textarea", d).value }) });
      j.note = $("textarea", d).value;
      toast("Note enregistrée", "", "");
    };
    $("[data-a=chart]", d).onclick = () => selectSignal(j);
  }
  $$("#f-side button").forEach((b) => b.addEventListener("click", () => {
    $$("#f-side button").forEach((x) => x.classList.toggle("on", x === b));
    F.side = b.dataset.v; renderJournal();
  }));
  $("#f-status").addEventListener("change", (e) => { F.status = e.target.value; renderJournal(); });
  $("#f-quality").addEventListener("change", (e) => { F.quality = e.target.value; renderJournal(); });

  /* ------------------------------------------------------------------ backtest */
  let eqChart = null, eqSeries = null;
  $("#bt-run").addEventListener("click", async () => {
    const btn = $("#bt-run");
    btn.disabled = true; btn.textContent = "Calcul en cours…";
    try {
      const body = { bars: +$("#bt-bars").value, strategy: {} };
      if ($("#bt-score").value !== "") body.strategy.min_score = +$("#bt-score").value;
      if ($("#bt-spread").value !== "") body.strategy.spread_pips = +$("#bt-spread").value;
      renderBacktest(await api("/api/backtest", { method: "POST", body: JSON.stringify(body) }));
    } catch (e) { toast("Backtest impossible", e.message, "err"); }
    finally { btn.disabled = false; btn.textContent = "Lancer le backtest"; }
  });

  function groupRows(rows, max) {
    return rows.map((g) => {
      const w = Math.min(50, (Math.abs(g.total_r) / max) * 50);
      const bar = g.total_r >= 0 ? `<i style="left:50%;width:${w}%;background:${C.up}"></i>` : `<i style="right:50%;width:${w}%;background:${C.down}"></i>`;
      return `<tr><td>${esc(g.key)}</td><td class="r">${g.trades}</td><td class="r">${g.win_rate.toFixed(0)} %</td>
        <td class="r ${g.expectancy_r >= 0 ? "up" : "down"}">${sgn(g.expectancy_r, 2)}</td>
        <td class="bar-cell"><div style="display:flex;align-items:center;gap:8px"><div class="hbar" style="flex:1"><span class="zero"></span>${bar}</div><span class="mono sm ${g.total_r >= 0 ? "up" : "down"}" style="width:62px;text-align:right">${sgn(g.total_r, 1)} R</span></div></td></tr>`;
    }).join("");
  }

  function renderBacktest(r) {
    const st = r.stats;
    $("#bt-empty").hidden = true;
    $("#bt-result").hidden = false;
    if (!st.trades) {
      $("#bt-kpis").innerHTML = `<div class="kpi"><span class="label">Trades</span><b>0</b><div class="hint">aucun signal sur la période</div></div>`;
      return;
    }
    const k = (label, val, hint, cls = "") => `<div class="kpi"><span class="label">${label}</span><b class="${cls}">${val}</b><div class="hint">${hint}</div></div>`;
    $("#bt-kpis").innerHTML =
      k("Trades", st.trades, Object.entries(st.exits).map(([a, b]) => `${a} ${b}`).join(" · ")) +
      k("Réussite", st.win_rate + " %", `gain moyen ${sgn(st.avg_win_r, 2)} R`) +
      k("Résultat", sgn(st.total_r, 1) + " R", `≈ ${sgn(st.total_r, 1)} % à 1 % de risque`, st.total_r >= 0 ? "up" : "down") +
      k("Espérance", sgn(st.expectancy_r, 3) + " R", "par trade", st.expectancy_r >= 0 ? "up" : "down") +
      k("Profit factor", st.profit_factor ?? "∞", st.profit_factor >= 1.3 ? "solide" : st.profit_factor >= 1 ? "fragile" : "perdant") +
      k("Drawdown max", "−" + st.max_drawdown_r + " R", `${st.max_losing_streak} pertes d'affilée max`, "down");
    $("#bt-period").textContent = `${fmtDate(r.period.start)} → ${fmtDate(r.period.end)} · ${r.period.bars.toLocaleString("fr-FR")} bougies · ${r.source}`;

    if (!eqChart) {
      eqChart = LWC.createChart($("#equity-chart"), { ...baseOpts, autoSize: true, localization: { locale: "fr-FR", priceFormatter: (p) => p.toFixed(1) + " R" } });
      eqSeries = eqChart.addBaselineSeries({ baseValue: { type: "price", price: 0 }, topLineColor: C.up, bottomLineColor: C.down,
        topFillColor1: "rgba(34,195,154,.25)", topFillColor2: "rgba(34,195,154,.02)", bottomFillColor1: "rgba(240,86,106,.02)", bottomFillColor2: "rgba(240,86,106,.25)", lineWidth: 2 });
    }
    const seen = new Set();
    const eq = r.equity.map((p) => ({ time: Math.floor(new Date(p.time).getTime() / 1000), value: p.value }))
      .filter((p) => !seen.has(p.time) && seen.add(p.time));
    eqSeries.setData(eq);
    eqChart.timeScale().fitContent();

    const maxP = Math.max(1, ...r.by_pattern.map((g) => Math.abs(g.total_r)));
    $("#bt-patterns tbody").innerHTML = groupRows(r.by_pattern, maxP);
    const maxQ = Math.max(1, ...r.by_quality.map((g) => Math.abs(g.total_r)));
    $("#bt-quality tbody").innerHTML = groupRows([...r.by_quality].sort((a, b) => ["A+", "A", "B"].indexOf(a.key) - ["A+", "A", "B"].indexOf(b.key)), maxQ);

    const hours = Object.fromEntries(r.by_hour.map((g) => [+g.key, g]));
    const maxH = Math.max(1, ...r.by_hour.map((g) => Math.abs(g.total_r)));
    let html = "";
    for (let h = 0; h < 24; h++) {
      const g = hours[h];
      const v = g ? g.total_r : 0;
      html += `<div class="h" title="${h}h : ${g ? g.trades + " trades, " + sgn(v, 1) + " R" : "aucun trade"}">
        <span class="v">${g ? sgn(v, 0) : ""}</span>
        <div class="col" style="height:${g ? Math.max(3, (Math.abs(v) / maxH) * 85) : 0}%;background:${v >= 0 ? C.up : C.down};opacity:${g ? 0.85 : 0}"></div>
        <span class="lab">${h}</span></div>`;
    }
    $("#bt-hours").innerHTML = html;

    $("#bt-trades tbody").innerHTML = r.trades.slice(0, 500).map((t) => `<tr>
      <td class="mono">${fmtDate(t.time)}</td><td><span class="side-badge ${t.side === "ACHAT" ? "buy" : "sell"}">${t.side === "ACHAT" ? "▲" : "▼"} ${t.side}</span></td>
      <td>${esc(t.pattern)}</td><td><span class="q-badge q-${t.quality}">${t.quality}</span> <span class="mono muted">${t.score}</span></td>
      <td class="r">${f5(t.entry)}</td><td>${statusPill(t.exit)}</td>
      <td class="r ${t.result_r > 0 ? "up" : t.result_r < 0 ? "down" : "muted"}">${sgn(t.result_r, 2)} R</td></tr>`).join("");
  }

  /* ------------------------------------------------------------------ réglages */
  const form = $("#settings-form");
  async function fillSettings() {
    try {
      [S.settings, S.meta] = await Promise.all([api("/api/settings"), S.meta ? S.meta : api("/api/meta")]);
    } catch (e) { toast("Réglages indisponibles", e.message, "err"); return; }
    const cfg = S.settings;
    for (const el of form.elements) {
      if (!el.name) continue;
      const v = el.name.startsWith("strategy.") ? cfg.strategy[el.name.slice(9)] : cfg[el.name];
      if (el.type === "checkbox") el.checked = !!v;
      else if (el.name === "strategy.sessions_utc") el.value = v.map(([a, b]) => `${a}-${b}`).join(", ");
      else el.value = v ?? "";
    }
    $("#ms-out").textContent = (+cfg.strategy.min_score).toFixed(1);
    $("#pattern-list").innerHTML = S.meta.patterns.map((p) => `<label><input type="checkbox" value="${esc(p)}" ${cfg.strategy.disabled_patterns.includes(p) ? "" : "checked"}>${esc(p)}</label>`).join("");
    $("#n-browser").checked = S.prefs.browser;
    $("#n-sound").checked = S.prefs.sound;
    $("#bt-score").placeholder = cfg.strategy.min_score;
    $("#bt-spread").placeholder = cfg.strategy.spread_pips;
    $("#save-msg").textContent = "";
  }
  form.elements["strategy.min_score"].addEventListener("input", (e) => { $("#ms-out").textContent = (+e.target.value).toFixed(1); });
  $("#reset-btn").addEventListener("click", fillSettings);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const out = { strategy: {} };
    try {
      for (const el of form.elements) {
        if (!el.name) continue;
        let v = el.type === "checkbox" ? el.checked : el.type === "number" || el.type === "range" ? +el.value : el.value.trim();
        if (el.name === "strategy.sessions_utc") {
          v = v ? v.split(",").map((p) => p.trim().split("-").map(Number)) : [];
          if (v.some((p) => p.length !== 2 || p.some(isNaN))) throw new Error("Sessions : écris par ex. 7-11, 12-17");
        }
        if (el.name.startsWith("strategy.")) out.strategy[el.name.slice(9)] = v; else out[el.name] = v;
      }
      out.strategy.disabled_patterns = $$("#pattern-list input").filter((i) => !i.checked).map((i) => i.value);
      $("#save-msg").textContent = "Enregistrement et nouvelle analyse…";
      S.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(out) });
      $("#save-msg").textContent = "✓ Réglages enregistrés dans config.yaml";
      toast("Réglages enregistrés", "L'analyse a été relancée avec les nouveaux paramètres.", "");
      loadState();
    } catch (err) {
      $("#save-msg").textContent = "";
      toast("Réglages refusés", err.message, "err");
    }
  });
  $("#n-browser").addEventListener("change", async (e) => { await setBrowserAlerts(e.target.checked); e.target.checked = S.prefs.browser; });
  $("#n-sound").addEventListener("change", (e) => { S.prefs.sound = e.target.checked; store.set("sound", S.prefs.sound); syncAlertBtn(); });

  /* ------------------------------------------------------------------ alertes */
  async function setBrowserAlerts(on) {
    if (on && "Notification" in window && Notification.permission !== "granted") {
      const p = await Notification.requestPermission();
      if (p !== "granted") { toast("Notifications refusées", "Autorise-les dans les réglages du navigateur.", "err"); on = false; }
    }
    S.prefs.browser = on; store.set("browser", on); syncAlertBtn();
  }
  function syncAlertBtn() {
    const on = S.prefs.browser || S.prefs.sound;
    $("#alerts-btn").classList.toggle("on", on);
    $("#alerts-btn").title = `Alertes : navigateur ${S.prefs.browser ? "activé" : "désactivé"}, son ${S.prefs.sound ? "activé" : "désactivé"}`;
  }
  $("#alerts-btn").addEventListener("click", async () => {
    const on = !(S.prefs.browser || S.prefs.sound);
    S.prefs.sound = on; store.set("sound", on);
    await setBrowserAlerts(on);
    toast(on ? "Alertes activées" : "Alertes coupées", on ? "Son + notification du navigateur à chaque signal." : "", "");
  });

  let audio;
  function beep(dir) {
    if (!S.prefs.sound) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const notes = dir === 1 ? [660, 880] : [880, 660];
      notes.forEach((f, k) => {
        const o = audio.createOscillator(), g = audio.createGain();
        o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, audio.currentTime + k * 0.18);
        g.gain.exponentialRampToValueAtTime(0.25, audio.currentTime + k * 0.18 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + k * 0.18 + 0.16);
        o.connect(g).connect(audio.destination);
        o.start(audio.currentTime + k * 0.18); o.stop(audio.currentTime + k * 0.18 + 0.18);
      });
    } catch { /* audio indisponible */ }
  }

  function onSignal(sig) {
    const buy = sig.direction === 1;
    const title = `${buy ? "▲ ACHAT" : "▼ VENTE"} EURUSD — ${sig.quality} (${sig.score}/10)`;
    const body = `${sig.pattern} · Entrée ${f5(sig.entry)} · SL ${f5(sig.sl)} · TP ${f5(sig.tp1)}`;
    toast(title, body, buy ? "buy" : "sell", 15000);
    beep(sig.direction);
    if (S.prefs.browser && "Notification" in window && Notification.permission === "granted") {
      const n = new Notification(title, { body, tag: sig.key });
      n.onclick = () => { window.focus(); n.close(); };
    }
  }

  function toast(title, body, kind = "", ms = 4500) {
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.innerHTML = `<b>${esc(title)}</b>${body ? `<div class="muted">${esc(body)}</div>` : ""}`;
    $("#toasts").append(el);
    setTimeout(() => el.remove(), ms);
    el.addEventListener("click", () => el.remove());
  }
  function banner(msg) {
    $("#error-banner").hidden = !msg;
    if (msg) $("#error-banner").textContent = "⚠ " + msg;
  }
  function setFeed(kind, label) {
    $("#feed").className = "feed " + kind;
    $("#feed-label").textContent = label;
  }

  /* ------------------------------------------------------------------ temps réel */
  function connect() {
    const es = new EventSource("/api/stream");
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.type === "update") { loadState(); if (S.view === "signaux") loadJournal(); }
      else if (ev.type === "signal") onSignal(ev.signal);
      else if (ev.type === "error") { banner(ev.message); setFeed("err", "Erreur données"); }
    };
    es.onerror = () => setFeed("err", "Reconnexion…");
    es.onopen = () => S.snap && setFeed(S.snap.source === "demo" ? "demo" : "live", S.snap.source_label);
  }

  $("#scan-btn").addEventListener("click", async () => {
    const b = $("#scan-btn");
    b.disabled = true; b.classList.add("loading");
    try {
      const r = await api("/api/scan", { method: "POST" });
      if (r.error) toast("Analyse impossible", r.error, "err");
    } catch (e) { toast("Analyse impossible", e.message, "err"); }
    finally { b.disabled = false; b.classList.remove("loading"); }
  });

  setInterval(() => {
    const now = new Date();
    const s = 300 - ((now.getUTCMinutes() % 5) * 60 + now.getUTCSeconds());
    $("#countdown").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);

  syncAlertBtn();
  loadState().then(() => api("/api/journal").then((d) => { S.journal = d.signals; }).catch(() => {}));
  connect();
})();
