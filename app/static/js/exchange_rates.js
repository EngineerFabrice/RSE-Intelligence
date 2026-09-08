(async function () {
  const body = document.getElementById("fxBody");
  try {
    const resp = await RSE.get("/api/exchange-rates");
    const items = resp.data;
    body.innerHTML = items.length ? items.map(f => `<tr>
      <td>${f.currency}</td>
      <td class="text-end">${RSE.fmt(f.buy_rate)}</td>
      <td class="text-end">${RSE.fmt(f.sell_rate)}</td>
      <td class="text-end">${RSE.fmt(f.average_rate)}</td>
    </tr>`).join("") : `<tr><td colspan="4" class="text-center text-muted py-4">No exchange rate data available yet.</td></tr>`;
  } catch (e) {
    body.innerHTML = `<tr><td colspan="4" class="text-center text-danger py-4">${e.message}</td></tr>`;
  }
})();
