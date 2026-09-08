(function () {
  const app = document.getElementById("app");
  const reportId = app.dataset.reportId;
  const tabContent = document.getElementById("tabContent");
  const reportMeta = document.getElementById("reportMeta");
  const approveBtn = document.getElementById("approveBtn");
  const sourceModalEl = document.getElementById("sourceModal");
  const sourceModal = sourceModalEl ? new bootstrap.Modal(sourceModalEl) : null;
  const sourceModalBody = document.getElementById("sourceModalBody");
  let previewData = null;
  let activeTab = "stock";

  function sourceLink(table, id) {
    if (id === undefined || id === null) return "—";
    return `<a href="#" class="small" onclick="event.preventDefault(); RSE_showSource('${table}', ${id})">Source</a>`;
  }

  const RENDERERS = {
    stock: (data) => table(
      ["ISIN", "Stock", "12m High", "12m Low", "Today High", "Today Low", "Closing", "Prev.", "Change", "Volume", "Value", ""],
      data.stock,
      (e) => [e.isin, e.symbol, RSE.fmt(e.high_12m), RSE.fmt(e.low_12m), RSE.fmt(e.today_high), RSE.fmt(e.today_low), RSE.fmt(e.closing_price), RSE.fmt(e.previous_close),
        `<span class="${RSE.changeClass(e.change)}">${RSE.fmt(e.change)}</span>`,
        RSE.fmtInt(e.volume), RSE.fmt(e.value_turnover), sourceLink("equities", e.id)]
    ),
    indices: (data) => table(
      ["Index", "Previous", "Today", "Points", "% Change"], data.indices,
      (i) => [i.index_name, RSE.fmt(i.previous_value), RSE.fmt(i.current_value), RSE.fmt(i.change), RSE.fmt(i.percentage_change)]
    ),
    market_stats: (data) => {
      if (!data.market_stats) return emptyState("No market statistics extracted for this report.");
      const s = data.market_stats;
      const rows = [
        ["Shares Traded", RSE.fmtInt(s.shares_traded)],
        ["Equity Turnover", RSE.fmt(s.equity_turnover)],
        ["Bond Turnover", RSE.fmt(s.bond_turnover)],
        ["Number of Deals", RSE.fmtInt(s.number_of_deals)],
        ["Market Capitalization", RSE.fmt(s.market_capitalization)],
        ["Repo Value", RSE.fmt(s.repo_value)],
      ];
      let html = `<table class="table mb-0"><tbody>` +
        rows.map(r => `<tr><th class="text-muted fw-normal" style="width:40%">${r[0]}</th><td>${r[1]}</td></tr>`).join("") +
        `</tbody></table>` +
        `<div class="px-3 pb-2">${sourceLink("market_statistics", s.id)}</div><hr>`;
      html += table(["Index", "Current", "Previous", "% Change"], data.indices,
        (i) => [i.index_name, RSE.fmt(i.current_value), RSE.fmt(i.previous_value),
          `<span class="${RSE.changeClass(i.percentage_change)}">${RSE.fmt(i.percentage_change)}%</span>`], true);
      return html;
    },
    bonds: (data) => table(
      ["ISIN", "Security", "Maturity", "Coupon", "Close/Yield", "Status", ""],
      data.bonds,
      (b) => [b.isin, b.security, b.maturity_date, RSE.fmt(b.coupon), RSE.fmt(b.close_price), b.status, sourceLink("bonds", b.id)]
    ),
    bond_trades: (data) => table(
      ["Trade Date", "ISIN", "Security", "Price/Yield", "Volume", "Value"],
      data.bond_trades,
      (t) => [t.trade_date, t.isin, t.security, RSE.fmt(t.price_yield), RSE.fmtInt(t.volume), RSE.fmt(t.value)]
    ),
    exchange_rates: (data) => table(
      ["Currency", "Buy", "Sell", "Average", ""],
      data.exchange_rates,
      (f) => [f.currency, RSE.fmt(f.buy_rate), RSE.fmt(f.sell_rate), RSE.fmt(f.average_rate), sourceLink("exchange_rates", f.id)]
    ),
    closing_bell: (data) => table(
      ["Security", "Bid Qty", "Bid Price", "Offer Qty", "Offer Price", "Status"],
      data.closing_bell,
      (c) => [c.security, RSE.fmtInt(c.bid_quantity), RSE.fmt(c.bid_price), RSE.fmtInt(c.offer_quantity), RSE.fmt(c.offer_price), c.status]
    ),
  };

  function emptyState(msg) {
    return `<div class="text-center text-muted py-5">${msg}</div>`;
  }

  function table(headers, rows, rowFn, plain) {
    if (!rows || !rows.length) return emptyState("No data extracted for this section.");
    const thead = `<thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>`;
    const tbody = `<tbody>${rows.map(r => `<tr>${rowFn(r).map(c => `<td>${c ?? "—"}</td>`).join("")}</tr>`).join("")}</tbody>`;
    return `<table class="table ${plain ? "" : "table-hover"} mb-0">${thead}${tbody}</table>`;
  }

  function render() {
    tabContent.innerHTML = `<div class="report-section-label">${sectionTitle(activeTab)}</div>` + RENDERERS[activeTab](previewData);
  }

  function sectionTitle(tab) {
    return {
      stock: "Equities",
      indices: "Indices",
      market_stats: "Market overview and statistics",
      bonds: "Bonds",
      bond_trades: "Bond trades",
      exchange_rates: "Exchange rates",
      closing_bell: "Closing bell",
    }[tab] || "Report section";
  }

  function hideEmptyTabs(data) {
    const available = {
      stock: data.stock,
      indices: data.indices,
      market_stats: data.market_stats,
      bonds: data.bonds,
      bond_trades: data.bond_trades,
      exchange_rates: data.exchange_rates,
      closing_bell: data.closing_bell,
    };
    document.querySelectorAll("#previewTabs button").forEach((button) => {
      const present = available[button.dataset.target];
      button.closest(".nav-item").classList.toggle("d-none", !present || (Array.isArray(present) && !present.length));
    });
  }

  document.querySelectorAll("#previewTabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#previewTabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.dataset.target;
      render();
    });
  });

  if (approveBtn) {
    approveBtn.addEventListener("click", async () => {
      try {
        await RSE.post(`/api/reports/${reportId}/approve`);
        location.reload();
      } catch (e) {
        alert(e.message);
      }
    });
  }

  // Source traceability (spec §4): shows the original PDF page, section, extraction
  // method, raw source text, and validation status behind one extracted record.
  window.RSE_showSource = async function (table, id) {
    if (!sourceModal) return;
    sourceModalBody.innerHTML = "Loading…";
    sourceModal.show();
    try {
      const resp = await RSE.get(`/api/reports/${reportId}/source?table=${table}&id=${id}`);
      const fields = resp.data.fields;
      if (!fields.length) {
        sourceModalBody.innerHTML = `<p class="text-muted mb-0">No lineage was recorded for this record.</p>`;
        return;
      }
      sourceModalBody.innerHTML = `
        <p class="small text-muted">Source document: <strong>${resp.data.original_filename}</strong></p>
        <table class="table table-sm mb-0">
          <thead><tr><th>Field</th><th>Value</th><th>Page</th><th>Method</th><th>Validated</th></tr></thead>
          <tbody>
            ${fields.map(f => `<tr>
              <td>${f.field_name}</td>
              <td>${f.value ?? "—"}</td>
              <td>${f.source_page ?? "—"}</td>
              <td>${(f.extraction_method || "—").replace(/_/g, " ")}</td>
              <td>${f.validation_status === "passed" ? "✓" : f.validation_status === "failed" ? "⚠" : "—"}</td>
            </tr>${f.source_text ? `<tr><td colspan="5" class="small text-muted">Source text: "${f.source_text}"</td></tr>` : ""}`).join("")}
          </tbody>
        </table>
      `;
    } catch (e) {
      sourceModalBody.innerHTML = `<p class="text-danger mb-0">Could not load source information: ${e.message}</p>`;
    }
  };

  RSE.get(`/api/reports/${reportId}/preview`).then((resp) => {
    previewData = resp.data;
    hideEmptyTabs(previewData);
    const r = previewData.report;
    reportMeta.textContent =
      `Report Date: ${r.report_date || "Unknown"} · Status: ${r.status_label} · ` +
      `Open Issues: ${previewData.open_issue_count}`;
    render();
  }).catch((e) => {
    tabContent.innerHTML = emptyState("Could not load preview data: " + e.message);
  });
})();
