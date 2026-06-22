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

  function asArray(value) {
    if (!value) return [];
    return Array.isArray(value) ? value : [value];
  }

  function valueText(value) {
    if (value === undefined || value === null || value === "") return "";
    if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(", ");
    if (typeof value === "object") {
      return Object.entries(value)
        .map(([key, item]) => `${labelize(key)}: ${valueText(item)}`)
        .filter(Boolean)
        .join("; ");
    }
    return String(value);
  }

  function safePersonalityLabel(value) {
    const text = String(value || "").trim();
    const labels = {
      dove: "Calm / Reasonable",
      eagle: "Straightforward / Bold",
      peacock: "Expressive / Social",
      owl: "Analytical / Observant",
    };
    return labels[text.toLowerCase()] || text;
  }

  function renderItems(value, limit = 8) {
    const items = asArray(value).slice(0, limit).map((item) => {
      if (item && typeof item === "object") {
        const label = item.name || item.label || item.title || "";
        const detail = item.indication || item.summary || item.description || item.advice || "";
        return `<li><strong>${label || "Item"}</strong>${detail ? `<span>${detail}</span>` : ""}</li>`;
      }
      return `<li>${valueText(item)}</li>`;
    });
    return items.length ? `<ul class="item-list">${items.join("")}</ul>` : empty("No items available");
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
        <div class="detail-card">
          <div class="row">
            <strong>${labelize(key)}</strong>
            <span>${item.score ?? "--"}</span>
            <span class="pill ${attention ? "attention" : ""}">${status || "Status"}</span>
          </div>
          ${item.functional_summary ? `<p>${item.functional_summary}</p>` : ""}
        </div>
      `;
    }).join("") || empty("No system scores available");
  }

  function renderFunctionalSystems(targetId, systems = {}, summaries = {}) {
    const merged = Object.entries(systems || {}).reduce((out, [key, item]) => {
      out[key] = {
        ...(item || {}),
        functional_summary: item?.functional_summary || summaries?.[key] || "",
      };
      return out;
    }, {});
    renderSystems(targetId, merged);
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

  function renderWellnessOfferings(targetId, offerings = {}, wellness = {}, food = {}) {
    const node = $(targetId);
    if (!node) return;
    const source = Object.keys(offerings || {}).length ? offerings : {
      nutrition: {
        summary: wellness.diet,
        recommended: food.diet?.recommended || [],
        avoid: food.diet?.avoid || [],
        functional_foods: food.functional_foods || [],
      },
      movement: {
        yoga: food.yoga || wellness.yoga,
        physical_activity: wellness.physicalActivity,
      },
      recovery: {
        sleep: wellness.sleep,
        stress: wellness.stress,
      },
      support: {
        supplements: wellness.supplements,
        medicine: wellness.medicine,
        medicines: food.medicines || [],
        herbal_support: food.herbal_support || [],
      },
      lifestyle: food.lifestyle || {},
      priority_systems: food.priority_systems || [],
    };

    const nutrition = source.nutrition || {};
    const movement = source.movement || {};
    const recovery = source.recovery || {};
    const support = source.support || {};
    const lifestyle = source.lifestyle || {};
    node.innerHTML = `
      <div class="section-grid">
        <div class="detail-card">
          <h3>Nutrition</h3>
          ${nutrition.summary ? `<p>${nutrition.summary}</p>` : ""}
          <h4>Recommended</h4>
          ${renderItems(nutrition.recommended, 10)}
          <h4>Avoid</h4>
          ${renderItems(nutrition.avoid, 8)}
        </div>
        <div class="detail-card">
          <h3>Functional Foods</h3>
          ${renderItems(nutrition.functional_foods, 8)}
        </div>
        <div class="detail-card">
          <h3>Movement</h3>
          <h4>Yoga</h4>
          ${renderItems(movement.yoga, 8)}
          ${movement.physical_activity ? `<p>${movement.physical_activity}</p>` : ""}
        </div>
        <div class="detail-card">
          <h3>Recovery</h3>
          ${recovery.sleep ? `<p><strong>Sleep:</strong> ${recovery.sleep}</p>` : ""}
          ${recovery.stress ? `<p><strong>Stress:</strong> ${recovery.stress}</p>` : ""}
        </div>
        <div class="detail-card">
          <h3>Support</h3>
          ${support.supplements ? `<p><strong>Supplements:</strong> ${support.supplements}</p>` : ""}
          ${support.medicine ? `<p><strong>Medicine:</strong> ${support.medicine}</p>` : ""}
          ${renderItems(support.medicines, 8)}
          <h4>Herbal Support</h4>
          ${renderItems(support.herbal_support, 10)}
        </div>
        <div class="detail-card">
          <h3>Lifestyle</h3>
          <h4>Do</h4>
          ${renderItems(lifestyle.dos, 8)}
          <h4>Avoid</h4>
          ${renderItems(lifestyle.donts, 8)}
        </div>
      </div>
    `;
  }

  function renderDmit(targetId, dmitData = {}) {
    const node = $(targetId);
    if (!node) return;
    const dmit = dmitData.dmit_summary || dmitData.dmit || dmitData || {};
    if (dmit.available === false || !Object.keys(dmit).length) {
      node.innerHTML = empty("DMIT data is not available for this report.");
      return;
    }
    const dominance = dmit.brain_dominance || {};
    const tfrc = dmit.tfrc || {};
    const personality = dmit.personality || {};
    const planning = dmit.planning || {};
    const learning = dmit.learning_styles || {};
    const intelligences = Object.entries(dmit.multiple_intelligences || {})
      .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
      .slice(0, 8);
    const lobes = Object.entries(dmit.brain_lobes || {})
      .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
    const swot = dmit.swot || {};

    node.innerHTML = `
      <div class="grid-4">
        <div class="metric"><span>Left Brain</span><strong>${dominance.left_pct ?? "--"}%</strong></div>
        <div class="metric"><span>Right Brain</span><strong>${dominance.right_pct ?? "--"}%</strong></div>
        <div class="metric"><span>TFRC Total</span><strong>${tfrc.total ?? "--"}</strong></div>
        <div class="metric"><span>Personality</span><strong>${[safePersonalityLabel(personality.primary), safePersonalityLabel(personality.secondary)].filter(Boolean).join(" / ") || "--"}</strong></div>
      </div>
      <div class="section-grid">
        <div class="detail-card">
          <h3>Learning Style</h3>
          ${renderItems(Object.entries(learning).map(([key, value]) => `${labelize(key)} ${value}%`), 6)}
        </div>
        <div class="detail-card">
          <h3>Planning</h3>
          <p>Doing ${planning.doing_pct ?? "--"}% | Planning ${planning.planning_pct ?? "--"}%</p>
        </div>
        <div class="detail-card">
          <h3>Multiple Intelligences</h3>
          ${renderItems(intelligences.map(([key, value]) => `${labelize(key)} ${value}`), 8)}
        </div>
        <div class="detail-card">
          <h3>Brain Lobes</h3>
          ${renderItems(lobes.map(([key, value]) => `${labelize(key)} ${value}%`), 8)}
        </div>
        ${["strengths", "weaknesses", "opportunities", "threats"].map((key) => `
          <div class="detail-card">
            <h3>${labelize(key)}</h3>
            ${renderItems(swot[key], 8)}
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderBiorhythm(targetId, biorhythm = {}) {
    const node = $(targetId);
    if (!node) return;
    const calendar = biorhythm.biorhythm_calendar || biorhythm.calendar || biorhythm || {};
    const today = calendar.today || {};
    const interpretation = today.interpretation || today;
    const watchDays = calendar.watch_days || [];
    const days = calendar.days || [];
    const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const blanks = Array.from({ length: calendar.first_weekday || 0 }, () => `<div class="day-cell empty"></div>`);
    node.innerHTML = `
      <div class="status ok">${calendar.month_name || "No month available"}</div>
      <div class="status">${interpretation.title ? `${interpretation.title}: ${interpretation.action || interpretation.summary || ""}` : "No today interpretation"}</div>
      <div class="calendar-grid">
        ${days.length ? weekdays.map((day) => `<div class="weekday">${day}</div>`).join("") : ""}
        ${blanks.join("")}
        ${days.map((day) => {
          const item = day.interpretation || {};
          return `
            <div class="day-cell ${day.type || ""}">
              <span class="day-number">${day.day}</span>
              <span class="cycle-row">
                ${["physical", "emotional", "intellectual"].map((cycle) => `
                  <span class="cycle-chip ${day[cycle]?.state || ""}">${day[cycle]?.short || cycle[0].toUpperCase()} ${day[cycle]?.percent ?? "--"}%</span>
                `).join("")}
              </span>
              <strong class="day-title">${item.title || day.type || "Biorhythm"}</strong>
              <span class="day-note">${item.summary || item.action || ""}</span>
            </div>
          `;
        }).join("") || empty("No day-by-day calendar available")}
      </div>
      <div class="list">
        ${watchDays.slice(0, 12).map((day) => `
          <div class="detail-card">
            <div class="row">
              <strong>Day ${day.day}</strong>
              <span>${day.type || ""}</span>
              <span class="pill attention">${day.label || "Watch"}</span>
            </div>
            <p>${day.summary || day.advice || ""}</p>
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
    renderFunctionalSystems,
    renderWellness,
    renderWellnessOfferings,
    renderDmit,
    renderBiorhythm,
    renderHistory,
    setupTabs,
    showJson,
  };
})();
