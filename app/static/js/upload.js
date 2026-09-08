(function () {
  const dropzone = document.getElementById("dropzone");
  const browseBtn = document.getElementById("browseBtn");
  const fileInput = document.getElementById("fileInput");
  const progressCard = document.getElementById("progressCard");
  const progressHeading = document.getElementById("progressHeading");
  const progressFill = document.getElementById("progressFill");
  const progressMessage = document.getElementById("progressMessage");
  const progressPercent = document.getElementById("progressPercent");
  const resultBox = document.getElementById("resultBox");
  const errorBox = document.getElementById("errorBox");
  const errorMessage = document.getElementById("errorMessage");
  const retryBtn = document.getElementById("retryBtn");
  const selectedFile = document.getElementById("selectedFile");

  browseBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => { if (fileInput.files.length) uploadFile(fileInput.files[0]); });
  retryBtn.addEventListener("click", () => resetToDropzone());

  ["dragover", "dragenter"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length) uploadFile(files[0]);
  });
  dropzone.addEventListener("click", (e) => { if (e.target === browseBtn) return; fileInput.click(); });

  function resetToDropzone() {
    errorBox.classList.add("d-none");
    progressCard.classList.add("d-none");
    dropzone.classList.remove("d-none");
    if (selectedFile) selectedFile.classList.add("d-none");
    fileInput.value = "";
  }

  // Real, backend-driven progress only — the percentage always comes from the API's
  // computed `progress.percent` (app/services/progress.py), never a client-side timer.
  function renderProgress(progress, reportId) {
    const percent = Math.max(0, Math.min(100, progress.percent));
    progressFill.style.width = percent + "%";
    progressPercent.textContent = percent + "%";
    progressMessage.textContent = progress.message;

    if (progress.state === "done") {
      progressHeading.innerHTML = '<span class="check">✓</span> Report Ready';
      progressFill.classList.add("is-done");
      resultBox.classList.remove("d-none");
      resultBox.innerHTML = `
        <p class="text-muted mb-3">Your market report is ready to review.</p>
        <div class="ready-actions">
          <a href="/reports/${reportId}/preview" class="btn btn-primary btn-sm">Preview Report</a>
          <a href="/api/reports/${reportId}/export/excel" class="btn btn-outline-primary btn-sm">Download Excel</a>
          <a href="/api/reports/${reportId}/export/pdf" class="btn btn-outline-primary btn-sm">Download PDF</a>
        </div>`;
    }
  }

  async function pollReport(reportId) {
    try {
      const resp = await RSE.get(`/api/reports/${reportId}`);
      const report = resp.data;

      if (report.progress.state === "failed") {
        showError();
        return;
      }

      renderProgress(report.progress, reportId);

      if (report.progress.state !== "done") {
        setTimeout(() => pollReport(reportId), 1500);
      }
    } catch (e) {
      showError();
    }
  }

  function showError() {
    progressCard.classList.add("d-none");
    dropzone.classList.add("d-none");
    errorBox.classList.remove("d-none");
    errorMessage.textContent = "No market data was published from this file. Please try again or choose a different report.";
  }

  async function uploadFile(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showError();
      errorMessage.textContent = "Only PDF files are accepted.";
      return;
    }

    errorBox.classList.add("d-none");
    dropzone.classList.add("d-none");
    progressCard.classList.remove("d-none");
    if (selectedFile) {
      selectedFile.textContent = file.name;
      selectedFile.classList.remove("d-none");
    }
    progressFill.classList.remove("is-done");
    progressHeading.textContent = "Processing RSE Report";
    resultBox.classList.add("d-none");
    renderProgress({ percent: 3, message: "Uploading your report…", state: "uploading" }, null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const csrf = document.querySelector('meta[name="csrf-token"]').getAttribute("content");
      const resp = await fetch("/api/reports/upload", {
        method: "POST",
        headers: { "X-CSRFToken": csrf },
        body: formData,
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.message || "Upload failed.");
      renderProgress(body.data.progress, body.data.id);
      pollReport(body.data.id);
    } catch (e) {
      showError();
      errorMessage.textContent = e.message;
    }
  }
})();
