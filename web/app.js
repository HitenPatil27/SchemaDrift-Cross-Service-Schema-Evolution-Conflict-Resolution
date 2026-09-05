/**
 * SchemaDrift -- Unified Batch Audit Client Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const btnDatasets = document.querySelectorAll(".btn-dataset");
  const auditTbody = document.getElementById("audit-tbody");

  // Metrics
  const metricTotal = document.getElementById("metric-total");
  const metricSafe = document.getElementById("metric-safe");
  const metricStructural = document.getElementById("metric-structural");
  const metricHealed = document.getElementById("metric-healed");
  const metricContract = document.getElementById("metric-contract");

  // Filter buttons & counts
  const btnFilters = document.querySelectorAll(".btn-filter");
  const filterAllCnt = document.getElementById("filter-all-cnt");
  const filterHealedCnt = document.getElementById("filter-healed-cnt");
  const filterBlockedCnt = document.getElementById("filter-blocked-cnt");
  const filterSafeCnt = document.getElementById("filter-safe-cnt");

  // SRE Report modal
  const btnGenReport = document.getElementById("btn-gen-report");
  const reportModal = document.getElementById("report-modal");
  const modalReportContent = document.getElementById("modal-report-content");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnDoneModal = document.getElementById("btn-done-modal");
  const btnCopyReport = document.getElementById("btn-copy-report");

  // Current state
  let currentItems = [];
  let currentFilter = "ALL";
  let sampleDatasets = {};

  // --- Initial Load ---
  loadSampleDatasets();

  // --- Load Datasets from Backend ---
  async function loadSampleDatasets() {
    try {
      const resp = await fetch("/api/sample-datasets");
      const data = await resp.json();
      if (data.datasets && data.datasets.length > 0) {
        data.datasets.forEach((ds) => {
          sampleDatasets[ds.filename] = ds.data;
        });
        // Auto-run first dataset (Payment stream)
        const defaultDataset = sampleDatasets["payment_transactions_stream.json"] || data.datasets[0].data;
        processBatch(defaultDataset);
      }
    } catch (err) {
      console.error("Failed to load sample datasets:", err);
    }
  }

  // Quick Dataset Buttons
  btnDatasets.forEach((btn) => {
    btn.addEventListener("click", () => {
      btnDatasets.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const filename = btn.getAttribute("data-dataset");
      if (sampleDatasets[filename]) {
        processBatch(sampleDatasets[filename]);
      }
    });
  });

  // --- Drag & Drop / File Upload ---
  dropZone.addEventListener("click", () => fileInput.click());

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  });

  function handleFileUpload(file) {
    if (!file.name.endsWith(".json")) {
      alert("Please upload a valid .json file.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result);
        const records = Array.isArray(parsed) ? parsed : [parsed];
        btnDatasets.forEach((b) => b.classList.remove("active"));
        processBatch(records);
      } catch (err) {
        alert("Failed to parse JSON file: " + err.message);
      }
    };
    reader.readAsText(file);
  }

  // --- Process Batch Function ---
  async function processBatch(records) {
    auditTbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; padding: 40px; color: var(--cyan);">
          <div class="loading-spinner"></div> Ingesting & running ${records.length} records through Two-Layer Engine + Groq AI Synthesizer...
        </td>
      </tr>
    `;

    try {
      const resp = await fetch("/api/process-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ records }),
      });
      const data = await resp.json();

      if (data.error) {
        alert("Processing error: " + data.error);
        return;
      }

      currentItems = data.items || [];
      metricTotal.textContent = data.stats.total;
      metricSafe.textContent = data.stats.safe;
      metricStructural.textContent = data.stats.structural_blocked;
      metricHealed.textContent = data.stats.semantic_healed;
      metricContract.textContent = `Target Consumer Contract: ${data.consumer_contract}`;

      filterAllCnt.textContent = data.stats.total;
      filterHealedCnt.textContent = data.stats.semantic_healed;
      filterBlockedCnt.textContent = data.stats.structural_blocked;
      filterSafeCnt.textContent = data.stats.safe;

      renderTable();
    } catch (err) {
      console.error("Batch processing failed:", err);
      alert("Failed to process batch: " + err.message);
    }
  }

  // --- Filter Navigation ---
  btnFilters.forEach((btn) => {
    btn.addEventListener("click", () => {
      btnFilters.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.getAttribute("data-filter");
      renderTable();
    });
  });

  // --- Render 4-Stage Table ---
  function renderTable() {
    let filtered = currentItems;
    if (currentFilter !== "ALL") {
      filtered = currentItems.filter((item) => item.status === currentFilter);
    }

    if (filtered.length === 0) {
      auditTbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; padding: 30px; color: var(--text-dim);">
            No records matching the filter '${currentFilter}'.
          </td>
        </tr>
      `;
      return;
    }

    let html = "";
    filtered.forEach((item) => {
      const isBlocked = item.status === "STRUCTURAL_BREAK";
      const isHealed = item.status === "SEMANTIC_HEALED";

      const aiBoxClass = isBlocked ? "ai-box blocked" : (isHealed ? "ai-box" : "ai-box pass-through");
      const resultBoxClass = isBlocked ? "result-box blocked" : "result-box";

      html += `
        <tr>
          <!-- 1. Initial Input -->
          <td>
            <span class="record-id-tag">${escapeHtml(item.id)}</span>
            <div class="record-box">
              ${formatJsonHighlight(item.initial_input)}
            </div>
          </td>

          <!-- 2. Semantic Layer (Sender vs Receiver) -->
          <td>
            ${
              item.semantic_producer && item.semantic_consumer ? `
                <div class="semantic-compare-grid">
                  <!-- Producer / Sender Side -->
                  <div class="semantic-box sender-box">
                    <div class="semantic-header">
                      <span class="sem-tag sem-tag-sender">PRODUCER SENDER</span>
                      <span class="sem-field-name">${escapeHtml(item.field || '')}</span>
                    </div>
                    <div class="sem-card">
                      <div class="sem-row"><span class="sem-k">kind:</span> <span class="sem-v sem-kind">${escapeHtml(item.semantic_producer.kind)}</span></div>
                      <div class="sem-row"><span class="sem-k">value:</span> <span class="sem-v ${isHealed ? 'sem-mismatch' : 'sem-match'}">${escapeHtml(String(item.semantic_producer.value))}</span></div>
                      <div class="sem-row"><span class="sem-k">type:</span> <span class="sem-v sem-type">${escapeHtml(item.semantic_producer.type)}</span></div>
                    </div>
                  </div>

                  <!-- Center VS Divider -->
                  <div class="semantic-vs-center">
                    <span class="vs-badge ${isHealed ? 'vs-drift' : 'vs-match'}">
                      ${isHealed ? '⚡ DRIFT' : '✔ EQUAL'}
                    </span>
                  </div>

                  <!-- Consumer / Receiver Side -->
                  <div class="semantic-box receiver-box">
                    <div class="semantic-header">
                      <span class="sem-tag sem-tag-receiver">CONSUMER RECEIVER</span>
                      <span class="sem-field-name">${escapeHtml(item.field || '')}</span>
                    </div>
                    <div class="sem-card">
                      <div class="sem-row"><span class="sem-k">kind:</span> <span class="sem-v sem-kind">${escapeHtml(item.semantic_consumer.kind)}</span></div>
                      <div class="sem-row"><span class="sem-k">value:</span> <span class="sem-v sem-match">${escapeHtml(String(item.semantic_consumer.value))}</span></div>
                      <div class="sem-row"><span class="sem-k">type:</span> <span class="sem-v sem-type">${escapeHtml(item.semantic_consumer.type)}</span></div>
                    </div>
                  </div>
                </div>
              ` : `
                <div class="structural-break-card">
                  <div class="semantic-header">
                    <span class="badge badge-red">LAYER 1 STRUCTURAL BREAK</span>
                  </div>
                  <div class="drift-desc" style="color: #fca5a5; margin: 6px 0;">${escapeHtml(item.drift_caught)}</div>
                  <div class="structural-bypassed">⚠️ Blocked at Layer 1: Semantic Layer Bypassed (Missing '&lt;name&gt;_id')</div>
                </div>
              `
            }
          </td>

          <!-- 3. How AI Changed That -->
          <td>
            <div class="${aiBoxClass}">
              ${escapeHtml(item.ai_intervention)}
            </div>
          </td>

          <!-- 4. Final Result -->
          <td>
            <div class="${resultBoxClass}">
              ${escapeHtml(item.final_result)}
            </div>
          </td>
        </tr>
      `;
    });

    auditTbody.innerHTML = html;
  }

  // --- SRE Report Modal ---
  btnGenReport.addEventListener("click", async () => {
    reportModal.style.display = "flex";
    modalReportContent.innerHTML = `<div class="loading-spinner"></div> Synthesizing live SRE Incident Post-Mortem Report via Groq Qwen 3.8 27B...`;

    try {
      const resp = await fetch("/api/ai/report", { method: "POST" });
      const data = await resp.json();
      if (data.report) {
        modalReportContent.textContent = data.report;
      } else {
        modalReportContent.textContent = "Error generating report: " + (data.error || "Unknown error");
      }
    } catch (err) {
      modalReportContent.textContent = "Network error: " + err.message;
    }
  });

  btnCloseModal.addEventListener("click", () => (reportModal.style.display = "none"));
  btnDoneModal.addEventListener("click", () => (reportModal.style.display = "none"));

  btnCopyReport.addEventListener("click", () => {
    navigator.clipboard.writeText(modalReportContent.textContent);
    btnCopyReport.textContent = "Copied to Clipboard!";
    setTimeout(() => (btnCopyReport.textContent = "Copy Markdown Report"), 2000);
  });

  // Helper: Format JSON with highlight
  function formatJsonHighlight(obj) {
    if (!obj) return "{}";
    const entries = Object.entries(obj);
    return entries
      .map(([k, v]) => {
        const valStr = typeof v === "string" ? `"${escapeHtml(v)}"` : v;
        const isKeyField = ["amount", "temperature", "status", "latency"].includes(k);
        const style = isKeyField ? 'style="color: #F59E0B; font-weight: bold;"' : "";
        return `<div><span style="color: #94A3B8;">"${k}":</span> <span ${style}>${valStr}</span></div>`;
      })
      .join("");
  }

  function escapeHtml(str) {
    if (typeof str !== "string") return String(str);
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
});
