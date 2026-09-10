(function () {
  let history = [];
  let metricsChart = null;
  let compareChart = null;
  let activeMetric = "equity_turnover";
  // Institutional palette for light mode; a lighter variant for dark mode so
  // multi-series lines keep good contrast against a dark surface. Chart.js
  // draws to <canvas>, so it can't read CSS variables on its own -- these are
  // picked in JS based on the current theme instead.
  const COLORS_LIGHT = ["#1f4e78", "#b9770e", "#1e7d4f", "#a63232", "#5a3d8f"];
  const COLORS_DARK = ["#5e9ed6", "#e0a24a", "#4fc189", "#e0837e", "#a389d9"];

  const METRIC_LABELS = {
    equity_turnover: "Equity Turnover (Frw)",
    bond_turnover: "Bond Turnover (Frw)",
    shares_traded: "Shares Traded",
    market_capitalization: "Market Capitalization (Frw)",
  };

  function isDarkMode() {
    return document.documentElement.getAttribute("data-bs-theme") === "dark";
  }

  function seriesColors() {
    return isDarkMode() ? COLORS_DARK : COLORS_LIGHT;
  }

  function chartTheme() {
    const css = getComputedStyle(document.documentElement);
    return {
      line: css.getPropertyValue("--rse-chart-line").trim(),
      fill: css.getPropertyValue("--rse-chart-fill").trim(),
      grid: css.getPropertyValue("--rse-chart-grid").trim(),
      text: css.getPropertyValue("--rse-chart-text").trim(),
    };
  }

  function axisOptions(theme) {
    return {
      x: { ticks: { color: theme.text }, grid: { color: theme.grid } },
      y: { ticks: { color: theme.text }, grid: { color: theme.grid } },
    };
  }

  function renderMetricChart(metric) {
    activeMetric = metric;
    const theme = chartTheme();
    const ctx = document.getElementById("metricsChart").getContext("2d");
    if (metricsChart) metricsChart.destroy();
    metricsChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: history.map(h => h.report_date),
        datasets: [{
          label: METRIC_LABELS[metric],
          data: history.map(h => h[metric]),
          borderColor: theme.line,
          backgroundColor: theme.fill,
          tension: 0.25, fill: true, pointRadius: 2,
        }],
      },
      options: { responsive: true, plugins: { legend: { display: false } }, scales: axisOptions(theme) },
    });
  }

  document.addEventListener("rse:theme-changed", () => {
    if (metricsChart) renderMetricChart(activeMetric);
    if (compareChart) {
      const theme = chartTheme();
      const colors = seriesColors();
      compareChart.data.datasets.forEach((ds, i) => { ds.borderColor = colors[i % colors.length]; });
      compareChart.options.scales.x.ticks.color = theme.text;
      compareChart.options.scales.x.grid.color = theme.grid;
      compareChart.options.scales.y.ticks.color = theme.text;
      compareChart.options.scales.y.grid.color = theme.grid;
      compareChart.update();
    }
  });

  document.querySelectorAll("#metricSelector button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#metricSelector button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderMetricChart(btn.dataset.metric);
    });
  });

  async function loadHistory() {
    try {
      const resp = await RSE.get("/api/market/history");
      history = resp.data;
      renderMetricChart("equity_turnover");
    } catch (e) {
      document.getElementById("metricsChart").replaceWith(
        Object.assign(document.createElement("div"), { className: "text-muted text-center py-4", textContent: "No historical data available yet." })
      );
    }
  }

  async function loadInsights() {
    const box = document.getElementById("insightsBox");
    try {
      const resp = await RSE.get("/api/insights");
      const items = resp.data;
      box.innerHTML = items.length ? items.map(i => `
        <div class="mb-3 pb-3 border-bottom">
          <div class="fw-bold small text-uppercase text-muted">${i.title}</div>
          <div class="small">${i.explanation}</div>
        </div>`).join("") : `<div class="text-muted text-center py-3">No insights available for the latest report.</div>`;
    } catch (e) {
      box.innerHTML = `<div class="text-danger small">${e.message}</div>`;
    }
  }

  document.getElementById("compareBtn").addEventListener("click", async () => {
    const raw = document.getElementById("compareInput").value;
    const symbols = raw.split(",").map(s => s.trim().toUpperCase()).filter(Boolean).slice(0, 5);
    if (!symbols.length) return;

    const colors = seriesColors();
    const datasets = [];
    let labels = [];
    for (let i = 0; i < symbols.length; i++) {
      try {
        const resp = await RSE.get(`/api/equities/${symbols[i]}/history`);
        const h = resp.data.history;
        if (h.length > labels.length) labels = h.map(x => x.report_date);
        datasets.push({
          label: symbols[i],
          data: h.map(x => x.closing_price),
          borderColor: colors[i % colors.length],
          backgroundColor: "transparent",
          tension: 0.25, pointRadius: 2,
        });
      } catch (e) { /* skip unknown symbol */ }
    }

    const theme = chartTheme();
    const ctx = document.getElementById("compareChart").getContext("2d");
    if (compareChart) compareChart.destroy();
    compareChart = new Chart(ctx, { type: "line", data: { labels, datasets }, options: { responsive: true, scales: axisOptions(theme) } });
  });

  loadHistory();
  loadInsights();
})();
