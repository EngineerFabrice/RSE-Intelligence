(async function () {
  const container = document.getElementById("indicesCards");
  try {
    const resp = await RSE.get("/api/indices");
    const items = resp.data;
    if (!items.length) {
      container.innerHTML = `<div class="col-12 text-center text-muted py-5">No index data available yet.</div>`;
      return;
    }
    container.innerHTML = items.map((i) => `
      <div class="col-md-4">
        <div class="metric-card">
          <div class="metric-label">${i.index_name}</div>
          <div class="metric-value">${RSE.fmt(i.current_value)}</div>
          <div class="metric-sub ${RSE.changeClass(i.percentage_change)}">
            ${RSE.fmt(i.change)} (${RSE.fmt(i.percentage_change)}%)
          </div>
        </div>
      </div>`).join("");
  } catch (e) {
    container.innerHTML = `<div class="col-12 text-center text-danger py-5">${e.message}</div>`;
  }
})();
