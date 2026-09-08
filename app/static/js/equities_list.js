(function () {
  const body = document.getElementById("equitiesBody");
  const searchBox = document.getElementById("searchBox");
  let timer = null;

  function row(e) {
    return `<tr>
      <td><a href="/equities/${e.symbol}">${e.symbol}</a></td>
      <td>${e.security_name || "—"}</td>
      <td class="text-end">${RSE.fmt(e.high_12m)}</td>
      <td class="text-end">${RSE.fmt(e.low_12m)}</td>
      <td class="text-end">${RSE.fmt(e.closing_price)}</td>
      <td class="text-end ${RSE.changeClass(e.change)}">${RSE.fmt(e.change)}</td>
      <td class="text-end">${RSE.fmtInt(e.volume)}</td>
      <td class="text-end">${RSE.fmt(e.value_turnover)}</td>
    </tr>`;
  }

  async function load(q) {
    body.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">Loading…</td></tr>`;
    try {
      const resp = await RSE.get(`/api/equities?q=${encodeURIComponent(q || "")}`);
      const items = resp.data.items;
      body.innerHTML = items.length
        ? items.map(row).join("")
        : `<tr><td colspan="8" class="text-center text-muted py-4">No equities match your search.</td></tr>`;
    } catch (e) {
      body.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">${e.message}</td></tr>`;
    }
  }

  searchBox.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => load(searchBox.value), 300);
  });

  load("");
})();
