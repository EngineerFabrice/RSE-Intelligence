(function () {
  const app = document.getElementById("app");
  const symbol = app.dataset.symbol;
  let fullHistory = [];
  let chart = null;

  function metricCard(label, value, sub) {
    return `<div class="col-6 col-md-3"><div class="metric-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-sub">${sub || ""}</div>
    </div></div>`;
  }

  async function loadOverview() {
    try {
      const resp = await RSE.get(`/api/equities/${symbol}`);
      const e = resp.data;
      document.getElementById("titleBox").textContent = `${e.symbol} — ${e.security_name || ""}`;
      document.getElementById("subtitleBox").textContent =
        `ISIN: ${e.isin || "—"} · Report Date: ${e.report ? e.report.report_date : "—"}`;

      document.getElementById("overviewCards").innerHTML =
        metricCard("Closing Price", RSE.fmt(e.closing_price)) +
        metricCard("Previous Close", RSE.fmt(e.previous_close)) +
        metricCard("Change", `<span class="${RSE.changeClass(e.change)}">${RSE.fmt(e.change)}</span>`) +
        metricCard("Volume", RSE.fmtInt(e.volume), `Turnover: ${RSE.fmt(e.value_turnover)}`);

      document.getElementById("sourceBox").innerHTML =
        `Extraction Method: ${e.extraction_method || "—"}<br>` +
        `Source Page: ${e.source_page || "—"}<br>` +
        `Confidence: ${RSE.confidenceBadge(e.confidence_level)}`;
    } catch (err) {
      document.getElementById("subtitleBox").textContent = "Could not load security overview.";
    }
  }

  function renderChart(days) {
    let data = fullHistory;
    if (days !== "all") {
      data = fullHistory.slice(-days);
    }
    const ctx = document.getElementById("priceChart").getContext("2d");
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: data.map(h => h.report_date),
        datasets: [{
          label: "Closing Price",
          data: data.map(h => h.closing_price),
          borderColor: "#1f4e78",
          backgroundColor: "rgba(31,78,120,0.08)",
          tension: 0.25, fill: true, pointRadius: 2,
        }],
      },
      options: { responsive: true, plugins: { legend: { display: false } } },
    });
  }

  function renderHistoryTable() {
    const body = document.getElementById("historyBody");
    const rows = [...fullHistory].reverse().slice(0, 60);
    body.innerHTML = rows.length ? rows.map(h => `<tr>
      <td>${h.report_date}</td>
      <td class="text-end">${RSE.fmt(h.closing_price)}</td>
      <td class="text-end ${RSE.changeClass(h.change_percent)}">${RSE.fmt(h.change_percent)}%</td>
      <td class="text-end">${RSE.fmtInt(h.volume)}</td>
    </tr>`).join("") : `<tr><td colspan="4" class="text-center text-muted py-4">No trading history available.</td></tr>`;
  }

  async function loadHistory() {
    try {
      const resp = await RSE.get(`/api/equities/${symbol}/history`);
      fullHistory = resp.data.history;
      renderChart(30);
      renderHistoryTable();
    } catch (e) {
      document.getElementById("historyBody").innerHTML =
        `<tr><td colspan="4" class="text-center text-danger py-4">${e.message}</td></tr>`;
    }
  }

  document.querySelectorAll("#rangeSelector button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#rangeSelector button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const range = btn.dataset.range;
      renderChart(range === "all" ? "all" : parseInt(range, 10));
    });
  });

  loadOverview();
  loadHistory();
})();
