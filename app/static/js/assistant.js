(function () {
  const form = document.getElementById("assistantForm");
  const input = document.getElementById("assistantInput");
  const askBtn = document.getElementById("assistantAskBtn");
  const conversation = document.getElementById("assistantConversation");
  const emptyState = document.getElementById("assistantEmpty");

  document.querySelectorAll(".assistant-example-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      input.value = chip.textContent.trim();
      input.focus();
    });
  });

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function renderSource(source) {
    const verified = !!source.verified;
    const statusClass = verified ? "assistant-status-verified" : "assistant-status-review";
    const statusLabel = verified ? "✓ Verified" : `⚠ ${source.status || "Review Required"}`;
    return `
      <div class="assistant-source">
        <div class="assistant-source-row"><span>Source</span><strong>RSE Market Report</strong></div>
        <div class="assistant-source-row"><span>Date</span><strong>${escapeHtml(source.report_date || "Unknown")}</strong></div>
        <div class="assistant-source-row"><span>Section</span><strong>${escapeHtml(source.section || "—")}</strong></div>
        <div class="assistant-source-row"><span>Status</span><strong class="${statusClass}">${statusLabel}</strong></div>
        ${source.report_id ? `<a class="btn btn-outline-secondary btn-sm mt-2" href="/reports/${encodeURIComponent(source.report_id)}/preview">View Source Data</a>` : ""}
      </div>`;
  }

  function addEntry(question, result) {
    emptyState.classList.add("d-none");

    const entry = document.createElement("div");
    entry.className = "assistant-entry";

    const sources = Array.isArray(result.sources) ? result.sources : [];
    const sourcesHtml = sources.map(renderSource).join("");

    entry.innerHTML = `
      <div class="assistant-question">${escapeHtml(question)}</div>
      <div class="assistant-answer-card ${result.error ? "is-error" : ""}">
        <div class="assistant-answer-text">${escapeHtml(result.answer)}</div>
        ${sourcesHtml ? `<div class="assistant-sources">${sourcesHtml}</div>` : ""}
      </div>`;
    conversation.insertBefore(entry, conversation.firstChild);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || askBtn.disabled) return;

    askBtn.disabled = true;
    input.disabled = true;

    try {
      const resp = await RSE.post("/api/assistant/ask", { question });
      addEntry(question, resp.data);
      input.value = "";
    } catch (err) {
      addEntry(question, {
        answer: err.message || "Something went wrong. Please try again.",
        sources: [],
        error: true,
      });
    } finally {
      askBtn.disabled = false;
      input.disabled = false;
      input.focus();
    }
  });
})();
