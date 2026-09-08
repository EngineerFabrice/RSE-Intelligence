(async function () {
  const body = document.getElementById("cbBody");
  try {
    const resp = await RSE.get("/api/order-book");
    const items = resp.data;
    body.innerHTML = items.length ? items.map(c => `<tr>
      <td>${c.security}</td>
      <td class="text-end">${c.has_bid ? RSE.fmtInt(c.bid_quantity) : "—"}</td>
      <td class="text-end">${c.has_bid ? RSE.fmt(c.bid_price) : "No Bid"}</td>
      <td class="text-end">${c.has_offer ? RSE.fmtInt(c.offer_quantity) : "—"}</td>
      <td class="text-end">${c.has_offer ? RSE.fmt(c.offer_price) : "No Offer"}</td>
      <td>${c.status || "—"}</td>
    </tr>`).join("") : `<tr><td colspan="6" class="text-center text-muted py-4">No closing bell data available yet.</td></tr>`;
  } catch (e) {
    body.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">${e.message}</td></tr>`;
  }
})();
