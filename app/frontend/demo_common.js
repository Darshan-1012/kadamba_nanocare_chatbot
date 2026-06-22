const Demo = (() => {
  const $ = (id) => document.getElementById(id);

  function apiBase() {
    const input = $("apiBase");
    return (input ? input.value : "http://localhost:8000/api").replace(/\/+$/, "");
  }

  function setStatus(id, message, kind = "") {
    const node = $(id);
    if (!node) return;
    node.textContent = message;
    node.className = `status ${kind}`.trim();
  }

  function setBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    button.dataset.label = button.dataset.label || button.textContent;
    button.textContent = busy ? "Working..." : button.dataset.label;
  }

  async function parseResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || JSON.stringify(data));
      }
      return data;
    }
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response;
  }

  async function apiGet(path) {
    return parseResponse(await fetch(`${apiBase()}${path}`));
  }

  async function apiPost(path, body, doctorId) {
    const headers = {};
    if (doctorId) headers["X-Doctor-Id"] = doctorId;
    return parseResponse(await fetch(`${apiBase()}${path}`, { method: "POST", headers, body }));
  }

  async function apiPatch(path, data, doctorId) {
    const headers = { "Content-Type": "application/json" };
    if (doctorId) headers["X-Doctor-Id"] = doctorId;
    return parseResponse(await fetch(`${apiBase()}${path}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(data),
    }));
  }

  async function health(statusId = "status") {
    try {
      const data = await apiGet("/health");
      setStatus(statusId, `${data.service}: ${data.ollama || "running"}`, "ok");
    } catch (error) {
      setStatus(statusId, error.message, "err");
    }
  }

  function labelize(value) {
    return String(value || "")
      .replace(/([A-Z])/g, " $1")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function empty(text) {
    return `<div class="empty">${text}</div>`;
  }

  function dimensionsToScores(dimensions = {}) {
    return {
      physical: dimensions.physical?.score,
      psychological: dimensions.psychological?.score,
      emotional: dimensions.emotional?.score,
      spiritual: dimensions.spiritual?.score,
    };
  }

  function keyMetrics(metrics = {}) {
    const keys = [
      "weight", "bmi", "bodyFat", "heartRate", "bioEnergy",
      "energyReserve", "lfhfRatio", "nadiPulse",
    ];
    return keys.reduce((out, key) => {
      out[key] = metrics[key];
      return out;
    }, {});
  }

  function extractReport(payload = {}) {
    if (payload.report) return payload.report;
    if (payload.latest_report?.report) return payload.latest_report.report;
    return payload;
  }

  function extractSummary(payload = {}, report = {}) {
    return payload.summary || dimensionsToScores(report.dimensions || {});
  }

  function renderScores(targetId, summary) {
    const node = $(targetId);
    if (!node) return;
    node.innerHTML = Object.entries(summary || {}).map(([key, value]) => `
      <div class="score">
        <span>${labelize(key)}</span>
        <strong>${value ?? "--"}</strong>
      </div>
    `).join("") || empty("No scores available");
  }

  function renderMetrics(targetId, metrics) {
    const node = $(targetId);
    if (!node) return;
    node.innerHTML = Object.entries(metrics || {}).map(([key, value]) => `
      <div class="metric">
        <span>${labelize(key)}</span>
        <strong>${value ?? "--"}</strong>
      </div>
    `).join("") || empty("No metrics available");
  }

  function renderSystems(targetId, systems = {}) {
    const node = $(targetId);
    if (!node) return;
    node.innerHTML = Object.entries(systems || {}).map(([key, item]) => {
      const status = item.displayStatus || item.status || "";
      const attention = /attention|critical|high|low/i.test(status);
      return `
        <div class="row">
          <strong>${labelize(key)}</strong>
          <span>${item.score ?? "--"}</span>
          <span class="pill ${attention ? "attention" : ""}">${status || "Status"}</span>
        </div>
      `;
    }).join("") || empty("No system scores available");
  }

  function renderWellness(targetId, wellness = {}) {
    const node = $(targetId);
    if (!node) return;
    const rows = Object.entries(wellness || {}).filter(([, value]) => value);
    node.innerHTML = rows.map(([key, value]) => `
      <div class="row compact">
        <strong>${labelize(key)}</strong>
        <span>${Array.isArray(value) ? value.join(", ") : value}</span>
      </div>
    `).join("") || empty("No wellness recommendations available");
  }

  function renderBiorhythm(targetId, biorhythm = {}) {
    const node = $(targetId);
    if (!node) return;
    const calendar = biorhythm.calendar || biorhythm || {};
    const today = calendar.today || {};
    const interpretation = today.interpretation || today;
    const watchDays = calendar.watch_days || [];
    node.innerHTML = `
      <div class="status ok">${calendar.month_name || "No month available"}</div>
      <div class="status">${interpretation.title ? `${interpretation.title}: ${interpretation.action || interpretation.summary || ""}` : "No today interpretation"}</div>
      <div class="list">
        ${watchDays.slice(0, 12).map((day) => `
          <div class="row">
            <strong>Day ${day.day}</strong>
            <span>${day.type || ""}</span>
            <span class="pill attention">${day.label || "Watch"}</span>
          </div>
        `).join("") || empty("No watch days available")}
      </div>
    `;
  }

  function renderHistory(targetId, history = {}) {
    const node = $(targetId);
    if (!node) return;
    const dates = history.dates || [];
    const physical = history.dimensions?.physical || [];
    node.innerHTML = dates.map((date, index) => {
      const score = physical[index] ?? 0;
      return `
        <div class="history-item">
          <div class="row compact">
            <strong>${date}</strong>
            <span>Physical ${score ?? "--"}</span>
          </div>
          <div class="bar"><span style="width:${Math.max(0, Math.min(100, score || 0))}%"></span></div>
        </div>
      `;
    }).join("") || empty("No history available");
  }

  function setupTabs() {
    document.querySelectorAll(".tabs button").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".tabs button").forEach((node) => node.classList.remove("active"));
        document.querySelectorAll(".view").forEach((node) => node.classList.remove("active"));
        button.classList.add("active");
        $(button.dataset.tab)?.classList.add("active");
      });
    });
  }

  function showJson(targetId, payload) {
    const node = $(targetId);
    if (node) node.textContent = JSON.stringify(payload || {}, null, 2);
  }

  return {
    $,
    apiBase,
    setStatus,
    setBusy,
    apiGet,
    apiPost,
    apiPatch,
    health,
    labelize,
    empty,
    keyMetrics,
    extractReport,
    extractSummary,
    renderScores,
    renderMetrics,
    renderSystems,
    renderWellness,
    renderBiorhythm,
    renderHistory,
    setupTabs,
    showJson,
  };
})();
