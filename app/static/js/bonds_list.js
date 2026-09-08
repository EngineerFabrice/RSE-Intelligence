(function () {
  const content = document.getElementById("bondsContent");
  let activeTab = "all";

  function emptyState(msg) {
    return `<div class="text-center text-muted py-5">${msg}</div>`;
  }

  function bondsTable(bonds) {
    if (!bonds.length) return emptyState("No bonds found for this filter.");
    return `<table class="table table-hover mb-0">
      <thead><tr><th>ISIN</th><th>Security</th><th>Type</th><th>Maturity</th><th>Tenor</th><th class="text-end">Coupon</th><th class="text-end">Close/Yield</th></tr></thead>
      <tbody>${bonds.map(b => `<tr>
        <td>${b.isin || "—"}</td><td>${b.security}</td><td class="text-capitalize">${b.bond_type}</td>
        <td>${b.maturity_date || "—"}</td><td>${b.tenor || "—"}</td>
        <td class="text-end">${RSE.fmt(b.coupon)}</td><td class="text-end">${RSE.fmt(b.close_price)}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  function tradesTable(trades) {
    if (!trades.length) return emptyState("No bond trades recorded.");
    return `<table class="table table-hover mb-0">
      <thead><tr><th>Date</th><th>ISIN</th><th>Security</th><th class="text-end">Price/Yield</th><th class="text-end">Volume</th><th class="text-end">Value</th></tr></thead>
      <tbody>${trades.map(t => `<tr>
        <td>${t.trade_date || "—"}</td><td>${t.isin || "—"}</td><td>${t.security || "—"}</td>
        <td class="text-end">${RSE.fmt(t.price_yield)}</td><td class="text-end">${RSE.fmtInt(t.volume)}</td><td class="text-end">${RSE.fmt(t.value)}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  async function load() {
    content.innerHTML = emptyState("Loading…");
    try {
      if (activeTab === "trades") {
        const resp = await RSE.get("/api/bonds/trades");
        content.innerHTML = tradesTable(resp.data);
      } else {
        const url = activeTab === "all" ? "/api/bonds" : `/api/bonds?type=${activeTab}`;
        const resp = await RSE.get(url);
        content.innerHTML = bondsTable(resp.data);
      }
    } catch (e) {
      content.innerHTML = `<div class="text-center text-danger py-5">${e.message}</div>`;
    }
  }

  document.querySelectorAll("#bondTabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#bondTabs button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.dataset.target;
      load();
    });
  });

  load();
})();
