(function () {
  const app = document.getElementById("app");
  const reportId = app.dataset.reportId;
  const issueList = document.getElementById("issueList");

  function severityBadge(sev) {
    const cls = { critical: "danger", warning: "warning", informational: "secondary" }[sev] || "secondary";
    return `<span class="badge bg-${cls} text-uppercase">${sev}</span>`;
  }

  function renderIssue(issue) {
    const resolved = !!issue.resolution;
    const card = document.createElement("div");
    card.className = "card mb-2";
    card.innerHTML = `
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            ${severityBadge(issue.severity)}
            <span class="fw-bold ms-2">${issue.record_label || issue.field || issue.issue_type}</span>
            <div class="text-muted small mt-1">${issue.description || ""}</div>
          </div>
          <div class="text-end">
            ${resolved
              ? `<span class="badge bg-light text-dark border">Resolved: ${issue.resolution.replace('_',' ')}</span>`
              : ""}
          </div>
        </div>
        ${issue.extracted_value || issue.alternative_value ? `
        <div class="row mt-2 small">
          <div class="col-md-6">
            <div class="text-muted">Source A${issue.source_a_page ? " — Page " + issue.source_a_page : ""} (${issue.source_a_label || "Extracted"})</div>
            <div class="fw-bold">${issue.extracted_value ?? "—"}</div>
          </div>
          <div class="col-md-6">
            <div class="text-muted">Source B${issue.source_b_page ? " — Page " + issue.source_b_page : ""} (${issue.source_b_label || "Alternative"})</div>
            <div class="fw-bold">${issue.alternative_value ?? "—"}</div>
          </div>
        </div>` : ""}
        ${!resolved ? `
        <div class="mt-3 d-flex gap-2 flex-wrap" data-actions="${issue.id}">
          ${issue.extracted_value ? `<button class="btn btn-sm btn-outline-primary" data-action="chosen_a">Choose "${issue.extracted_value}"</button>` : ""}
          ${issue.alternative_value ? `<button class="btn btn-sm btn-outline-primary" data-action="chosen_b">Choose "${issue.alternative_value}"</button>` : ""}
          <button class="btn btn-sm btn-outline-secondary" data-action="corrected">Enter Correction</button>
          <button class="btn btn-sm btn-outline-secondary" data-action="dismissed">Dismiss</button>
        </div>` : ""}
      </div>
    `;

    if (!resolved) {
      card.querySelectorAll("[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => resolveIssue(issue, btn.dataset.action));
      });
    }
    return card;
  }

  async function resolveIssue(issue, resolution) {
    let resolved_value = null;
    let reason = null;
    if (resolution === "corrected") {
      resolved_value = prompt("Enter the corrected value:");
      if (resolved_value === null) return;
      reason = "manual_correction";
    } else if (resolution === "dismissed") {
      reason = prompt("Reason for dismissing (optional):") || "";
    }
    try {
      await RSE.post(`/api/reports/${reportId}/issues/${issue.id}/resolve`, { resolution, resolved_value, reason });
      loadIssues();
    } catch (e) {
      alert(e.message);
    }
  }

  async function loadIssues() {
    const resp = await RSE.get(`/api/reports/${reportId}/preview`);
    const issues = resp.data.issues || [];

    document.getElementById("criticalCount").textContent = issues.filter(i => i.severity === "critical" && !i.resolution).length;
    document.getElementById("warningCount").textContent = issues.filter(i => i.severity === "warning" && !i.resolution).length;
    document.getElementById("infoCount").textContent = issues.filter(i => i.severity === "informational" && !i.resolution).length;

    issueList.innerHTML = "";
    if (!issues.length) {
      issueList.innerHTML = `<div class="card"><div class="card-body text-center text-muted py-5">
        No extraction issues detected. This report is ready for approval.
      </div></div>`;
      return;
    }

    const open = issues.filter(i => !i.resolution).sort((a, b) => {
      const order = { critical: 0, warning: 1, informational: 2 };
      return order[a.severity] - order[b.severity];
    });
    const resolved = issues.filter(i => i.resolution);

    open.forEach((i) => issueList.appendChild(renderIssue(i)));
    if (resolved.length) {
      const heading = document.createElement("div");
      heading.className = "text-muted small text-uppercase mt-4 mb-2";
      heading.textContent = "Resolved";
      issueList.appendChild(heading);
      resolved.forEach((i) => issueList.appendChild(renderIssue(i)));
    }
  }

  loadIssues().catch((e) => {
    issueList.innerHTML = `<div class="alert alert-danger">Could not load issues: ${e.message}</div>`;
  });
})();
