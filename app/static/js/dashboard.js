(async function () {
  const canvas = document.getElementById("turnoverChart");
  if (!canvas) return;

  try {
    const resp = await RSE.get("/api/market/history");
    const history = resp.data || [];
    const labels = history.map((h) => h.report_date);
    const turnover = history.map((h) => h.equity_turnover);

    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Equity Turnover (Frw)",
          data: turnover,
          borderColor: "#1f4e78",
          backgroundColor: "rgba(31,78,120,0.08)",
          tension: 0.25,
          fill: true,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
  } catch (e) {
    canvas.replaceWith(Object.assign(document.createElement("div"), {
      className: "text-muted text-center py-4",
      textContent: "Historical turnover data isn't available yet.",
    }));
  }
})();
