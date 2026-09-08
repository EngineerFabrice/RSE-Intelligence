const RSE = (() => {
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  async function request(url, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    opts.headers = Object.assign({ "X-CSRFToken": csrfToken() }, opts.headers);
    const resp = await fetch(url, opts);
    let body = null;
    try { body = await resp.json(); } catch (e) { /* non-JSON response (e.g. file download) */ }
    if (!resp.ok) {
      const message = (body && body.message) || `Request failed (${resp.status})`;
      const err = new Error(message);
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  function get(url) { return request(url); }
  function post(url, data) {
    return request(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {}),
    });
  }

  function fmt(value, decimals = 2) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }

  function fmtInt(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString();
  }

  function changeClass(value) {
    if (value === null || value === undefined) return "change-flat";
    return value > 0 ? "change-positive" : value < 0 ? "change-negative" : "change-flat";
  }

  function confidenceBadge(level) {
    const labels = { high: "High Confidence", review_required: "Review Required", manual_correction: "Manual Correction" };
    return `<span class="badge badge-confidence-${level || "review_required"}">${labels[level] || "Unknown"}</span>`;
  }

  function statusBadge(status) {
    const label = (status || "").replace(/_/g, " ");
    return `<span class="badge badge-status-${status}">${label}</span>`;
  }

  return { get, post, request, fmt, fmtInt, changeClass, confidenceBadge, statusBadge };
})();
