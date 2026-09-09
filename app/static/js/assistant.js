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

  // Minimal Markdown -> HTML for assistant answers (headings, bold, tables,
  // bullet/numbered lists, horizontal rules). The raw text is HTML-escaped
  // first, so only the Markdown syntax we recognize below is ever turned
  // into markup -- everything else stays inert text.
  function inlineFormat(text) {
    return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function isTableSeparatorRow(line) {
    return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(line);
  }

  function splitTableRow(line) {
    let cells = line.trim();
    if (cells.startsWith("|")) cells = cells.slice(1);
    if (cells.endsWith("|")) cells = cells.slice(0, -1);
    return cells.split("|").map((c) => c.trim());
  }

  function renderMarkdown(raw) {
    const lines = escapeHtml(raw).split("\n");
    const blocks = [];
    let paragraphBuf = [];
    let listBuf = [];
    let listTag = null;

    function flushParagraph() {
      if (paragraphBuf.length) {
        blocks.push(`<p>${paragraphBuf.map(inlineFormat).join("<br>")}</p>`);
        paragraphBuf = [];
      }
    }
    function flushList() {
      if (listBuf.length) {
        blocks.push(`<${listTag}>${listBuf.map((item) => `<li>${inlineFormat(item)}</li>`).join("")}</${listTag}>`);
        listBuf = [];
        listTag = null;
      }
    }

    let i = 0;
    while (i < lines.length) {
      const trimmed = lines[i].trim();

      if (trimmed === "") {
        flushParagraph();
        flushList();
        i++;
        continue;
      }

      if (/^#{1,6}\s+/.test(trimmed)) {
        flushParagraph();
        flushList();
        blocks.push(`<h5 class="assistant-answer-heading">${inlineFormat(trimmed.replace(/^#{1,6}\s+/, ""))}</h5>`);
        i++;
        continue;
      }

      if (/^-{3,}$/.test(trimmed)) {
        flushParagraph();
        flushList();
        blocks.push('<hr class="assistant-answer-divider">');
        i++;
        continue;
      }

      if (trimmed.startsWith("|") && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1].trim())) {
        flushParagraph();
        flushList();
        const headerCells = splitTableRow(trimmed);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          rows.push(splitTableRow(lines[i].trim()));
          i++;
        }
        const thead = `<thead><tr>${headerCells.map((c) => `<th>${inlineFormat(c)}</th>`).join("")}</tr></thead>`;
        const tbody = `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inlineFormat(c)}</td>`).join("")}</tr>`).join("")}</tbody>`;
        blocks.push(`<div class="table-responsive"><table class="table table-sm assistant-answer-table">${thead}${tbody}</table></div>`);
        continue;
      }

      const bulletMatch = trimmed.match(/^[*-]\s+(.*)$/);
      const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);
      if (bulletMatch || orderedMatch) {
        const tag = bulletMatch ? "ul" : "ol";
        if (listTag && listTag !== tag) flushList();
        listTag = tag;
        listBuf.push((bulletMatch || orderedMatch)[1]);
        i++;
        continue;
      }

      flushList();
      paragraphBuf.push(trimmed);
      i++;
    }
    flushParagraph();
    flushList();
    return blocks.join("");
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
        <div class="assistant-answer-text">${renderMarkdown(result.answer)}</div>
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
