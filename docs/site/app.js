const $ = (sel) => document.querySelector(sel);
const fmtPct = (v) => (v == null || Number.isNaN(v) ? "—" : `${v.toFixed(2)}%`);
const fmtUsd = (v) => (v == null || Number.isNaN(v) ? "—" : `$${Number(v).toFixed(2)}`);
const cls = (v) => (v >= 0 ? "pos" : "neg");

async function getJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch ${path}: ${res.status}`);
  return res.json();
}

// --- Tabs ---
document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
  });
});

// --- Simulation tab ---
async function loadSimulation() {
  let summary, equity, open, trades;
  try {
    [summary, equity, open, trades] = await Promise.all([
      getJSON("./data/simulation/summary.json"),
      getJSON("./data/simulation/equity_curve.json"),
      getJSON("./data/simulation/open_positions.json"),
      getJSON("./data/simulation/trades.json"),
    ]);
  } catch (e) {
    $("#summary-cards").innerHTML = `<div class="card">No simulation data yet.</div>`;
    return;
  }

  $("#summary-cards").innerHTML = [
    ["누적 손익", fmtUsd(summary.total_pnl), summary.total_pnl],
    ["수익률", fmtPct(summary.total_return_pct), summary.total_return_pct],
    ["투입 자본", fmtUsd(summary.invested_capital), 0],
    ["승률", fmtPct(summary.win_rate), summary.win_rate],
    ["거래 / 보유", `${summary.num_trades} / ${summary.num_open}`, 0],
    ["최대 낙폭", fmtPct(summary.max_drawdown_pct), summary.max_drawdown_pct],
  ].map(([label, val, signed]) =>
    `<div class="card"><div>${label}</div><div class="big ${typeof signed === "number" && signed !== 0 ? cls(signed) : ""}">${val}</div></div>`
  ).join("");

  new Chart($("#equityChart"), {
    type: "line",
    data: {
      labels: equity.map((p) => p.date),
      datasets: [{ label: "누적 손익 ($)", data: equity.map((p) => p.pnl),
        borderColor: "#3fb950", backgroundColor: "rgba(63,185,80,.15)", fill: true, tension: .2 }],
    },
    options: { scales: { x: { ticks: { color: "#8b949e" } }, y: { ticks: { color: "#8b949e" } } },
      plugins: { legend: { labels: { color: "#e6e6e6" } } } },
  });

  // One unified row per recommendation: signal date -> entry -> status -> P&L.
  // Open positions (still held) carry unrealized P&L; closed trades carry realized P&L.
  const rows = [];
  for (const p of open) {
    rows.push({
      signal_date: p.signal_date, ticker: p.ticker, entry_date: p.entry_date,
      entry_price: p.entry_price, stop_loss: p.stop_loss, target: p.target,
      status: "보유중", current: p.mark_price, current_label: `${p.mark_date} 종가`,
      pnl_pct: p.unrealized_pnl_pct, pnl: p.unrealized_pnl,
    });
  }
  for (const t of trades) {
    rows.push({
      signal_date: t.signal_date, ticker: t.ticker, entry_date: t.entry_date,
      entry_price: t.entry_price, stop_loss: t.stop_loss, target: t.target,
      status: t.exit_reason === "target" ? "목표 청산" : "손절 청산",
      current: t.exit_price, current_label: `${t.exit_date} 청산`,
      pnl_pct: t.pnl_pct, pnl: t.pnl,
    });
  }
  // Sort by signal date (newest first), then ticker.
  rows.sort((a, b) => (b.signal_date || "").localeCompare(a.signal_date || "") ||
                      (a.ticker || "").localeCompare(b.ticker || ""));

  $("#positions-table tbody").innerHTML = rows.map((r) => {
    const held = r.status === "보유중";
    const badge = held ? "badge-open" : (r.status === "목표 청산" ? "badge-target" : "badge-stop");
    return `<tr>
      <td>${r.signal_date ?? "—"}</td>
      <td><strong>${r.ticker}</strong></td>
      <td>${r.entry_date}</td>
      <td>${fmtUsd(r.entry_price)}</td>
      <td>${fmtUsd(r.stop_loss)} / ${fmtUsd(r.target)}</td>
      <td><span class="badge ${badge}">${r.status}</span></td>
      <td>${fmtUsd(r.current)}<br/><span class="sub">${r.current_label}</span></td>
      <td class="${cls(r.pnl_pct)}"><strong>${fmtPct(r.pnl_pct)}</strong></td>
      <td class="${cls(r.pnl)}">${fmtUsd(r.pnl)}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="9">아직 거래가 없습니다.</td></tr>`;
}

// --- Report tab ---
async function loadReportIndex() {
  let index;
  try { index = await getJSON("./data/daily_scans/index.json"); }
  catch (e) { $("#market-line").textContent = "No scan data yet."; return; }
  const sel = $("#date-select");
  sel.innerHTML = index.dates.slice().reverse()
    .map((d) => `<option value="${d}">${d}</option>`).join("");
  sel.addEventListener("change", () => loadReport(sel.value));
  if (index.dates.length) loadReport(index.latest);
}

async function loadReport(date) {
  const scan = await getJSON(`./data/daily_scans/scan_${date}.json`);
  $("#market-line").textContent =
    `Buys: ${scan.counts.buy} · Sells: ${scan.counts.sell}` +
    (scan.market && scan.market.spy_phase != null ? ` · SPY Phase ${scan.market.spy_phase}` : "");

  $("#buy-cards").innerHTML = scan.buys.slice(0, 12).map((b) =>
    `<div class="card"><div class="big">#${b.rank} ${b.ticker}</div>
     <div>Score: ${b.score}</div><div>Phase ${b.phase ?? "—"} · ${b.entry_quality ?? ""}</div>
     <div>Stop ${fmtUsd(b.stop_loss)} → Target ${fmtUsd(b.target)}</div>
     <div>${(b.reasons || []).slice(0, 3).map((r) => "• " + r).join("<br/>")}</div></div>`
  ).join("") || `<div class="card">No buy signals.</div>`;

  $("#sell-cards").innerHTML = scan.sells.slice(0, 12).map((s) =>
    `<div class="card"><div class="big">#${s.rank} ${s.ticker}</div>
     <div>Score: ${s.score}</div><div>Phase ${s.phase ?? "—"} · ${s.severity ?? ""}</div>
     <div>Breakdown ${fmtUsd(s.breakdown_level)}</div></div>`
  ).join("") || `<div class="card">No sell signals.</div>`;
}

loadSimulation();
loadReportIndex();
