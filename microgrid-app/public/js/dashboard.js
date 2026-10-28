/**
 * Smart Energy Microgrid Dashboard – JavaScript
 * Handles: tabs, form submission, CSV upload, chart rendering, table population.
 */

"use strict";

// ── Config ──────────────────────────────────────────────────────────────────
// When deployed to Catalyst AppSail the API is on the same origin.
// Override with window.FORECAST_API_BASE if needed.
const API_BASE = window.FORECAST_API_BASE || "https://forecast-api-50047208133.development.catalystappsail.in";
// ── Clock ────────────────────────────────────────────────────────────────────
(function updateClock() {
  const el = document.getElementById("system-clock");
  function tick() {
    el.textContent = new Date().toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      hour12: false,
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }) + " IST";
  }
  tick();
  setInterval(tick, 1000);
})();

// ── Tab switching ────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.remove("hidden");
  });
});

// ── Pre-fill timestamp ───────────────────────────────────────────────────────
(function prefillTimestamp() {
  const el = document.getElementById("f-timestamp");
  const now = new Date();
  // round down to the hour
  now.setMinutes(0, 0, 0);
  el.value = now.toISOString().slice(0, 16);
})();

// ── CSV drag-and-drop & file picker ─────────────────────────────────────────
let uploadedFile = null;
const dropZone = document.getElementById("drop-zone");
const csvInput = document.getElementById("csv-input");

dropZone.addEventListener("click", () => csvInput.click());
dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave",  () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setUploadedFile(file);
});
csvInput.addEventListener("change", () => {
  if (csvInput.files[0]) setUploadedFile(csvInput.files[0]);
});
function setUploadedFile(file) {
  uploadedFile = file;
  document.getElementById("csv-filename").textContent = "📄 " + file.name;
}

// ── Chart instances ──────────────────────────────────────────────────────────
let demandChart = null;
let socChart    = null;

// ── Forecast: form ───────────────────────────────────────────────────────────
document.getElementById("btn-forecast-form").addEventListener("click", async () => {
  const ts      = document.getElementById("f-timestamp").value;
  const temp    = parseFloat(document.getElementById("f-temp").value);
  const humidity= parseFloat(document.getElementById("f-humidity").value);
  const solar   = parseFloat(document.getElementById("f-solar").value);

  if (!ts || isNaN(temp) || isNaN(humidity) || isNaN(solar)) {
    showError("Please fill in all fields before generating a forecast.");
    return;
  }

  const payload = {
    rows: [{
      timestamp: ts.replace("T", " ") + ":00",
      ambient_temp_c: temp,
      humidity_pct: humidity,
      solar_irradiance_wm2: solar,
    }],
  };

  await runForecast(() =>
    fetch(API_BASE + "/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
});

// ── Forecast: CSV ────────────────────────────────────────────────────────────
document.getElementById("btn-forecast-csv").addEventListener("click", async () => {
  if (!uploadedFile) {
    showError("Please select a CSV file first.");
    return;
  }
  const formData = new FormData();
  formData.append("file", uploadedFile);

  await runForecast(() =>
    fetch(API_BASE + "/upload", { method: "POST", body: formData })
  );
});

// ── Core forecast runner ─────────────────────────────────────────────────────
async function runForecast(fetchFn) {
  hideError();
  showLoading(true);
  try {
    const res  = await fetchFn();
    const data = await res.json();
    if (!res.ok || data.status !== "success") {
      const msg = data.message || (data.data && data.data.message) || `HTTP ${res.status}: Server error`;
      throw new Error(msg);
    }
    renderResults(data.forecast);
  } catch (err) {
    showError("Forecast failed: " + err.message);
  } finally {
    showLoading(false);
  }
}

// ── Render results ───────────────────────────────────────────────────────────
function renderResults(forecast) {
  // Show sections
  ["section-charts", "section-soc", "section-table"].forEach(id => {
    document.getElementById(id).style.display = "";
  });

  const labels    = forecast.map(r => `${r.hour}:00`);
  const demands   = forecast.map(r => r.demand_kw);
  const socValues = forecast.map(r => r.battery_soc_pct);
  const modes     = forecast.map(r => r.controller.mode);

  // ── status cards ──
  const peak = Math.max(...demands);
  const avg  = (demands.reduce((a, b) => a + b, 0) / demands.length).toFixed(1);
  const lastSoc = socValues[socValues.length - 1];

  // Determine dominant mode (most frequent in forecast)
  const renewableCount = modes.filter(m => m === "Renewable Storage").length;
  const dominantMode   = renewableCount > 12 ? "Renewable Storage" : "Main Grid";

  document.getElementById("val-peak").textContent = peak.toFixed(1);
  document.getElementById("val-avg").textContent  = avg;
  document.getElementById("val-soc").textContent  = lastSoc;
  document.getElementById("val-mode").textContent = dominantMode === "Renewable Storage" ? "🌱 Renewable" : "🔌 Main Grid";

  const modeCard = document.getElementById("card-mode");
  modeCard.classList.toggle("renewable", dominantMode === "Renewable Storage");
  modeCard.classList.toggle("maingrid",  dominantMode !== "Renewable Storage");

  // ── overload banner ──
  const hasOverload = demands.some(d => d >= 200);
  document.getElementById("overload-banner").classList.toggle("hidden", !hasOverload);

  // ── demand chart ──
  const bgColors = demands.map(d => d >= 200 ? "rgba(239,68,68,.25)" : d > 160 ? "rgba(245,158,11,.25)" : "rgba(79,142,247,.25)");
  const bdColors = demands.map(d => d >= 200 ? "#ef4444" : d > 160 ? "#f59e0b" : "#4f8ef7");

  if (demandChart) demandChart.destroy();
  demandChart = new Chart(document.getElementById("demand-chart"), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Demand (kW)",
        data: demands,
        backgroundColor: bgColors,
        borderColor: bdColors,
        borderWidth: 2,
        borderRadius: 4,
      }, {
        label: "Renewable threshold (160 kW)",
        data: Array(24).fill(160),
        type: "line",
        borderColor: "#f59e0b",
        borderDash: [6, 4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0,
        yAxisID: "y",
      }, {
        label: "Overload threshold (200 kW)",
        data: Array(24).fill(200),
        type: "line",
        borderColor: "#ef4444",
        borderDash: [6, 4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0,
        yAxisID: "y",
      }],
    },
    options: chartOptions("Demand (kW)"),
  });

  // ── SoC chart ──
  if (socChart) socChart.destroy();
  socChart = new Chart(document.getElementById("soc-chart"), {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Battery SoC (%)",
        data: socValues,
        borderColor: "#22c55e",
        backgroundColor: "rgba(34,197,94,.12)",
        borderWidth: 2.5,
        pointRadius: 3,
        fill: true,
        tension: 0.35,
      }],
    },
    options: chartOptions("Battery SoC (%)"),
  });

  // ── table ──
  const tbody = document.getElementById("forecast-tbody");
  tbody.innerHTML = "";
  forecast.forEach(row => {
    const mode    = row.controller.mode;
    const isOverload = row.controller.overload_alert;
    const tr = document.createElement("tr");
    if (isOverload) tr.style.background = "rgba(239,68,68,.07)";
    tr.innerHTML = `
      <td>${row.hour}:00</td>
      <td>${row.timestamp}</td>
      <td>${row.demand_kw.toFixed(2)}</td>
      <td><span class="badge ${mode === "Renewable Storage" ? "badge-renewable" : "badge-maingrid"}">${mode}</span></td>
      <td>${row.battery_soc_pct}</td>
      <td>${isOverload ? '<span class="badge badge-overload">⚠ OVERLOAD</span>' : '<span class="badge badge-ok">OK</span>'}</td>
    `;
    tbody.appendChild(tr);
  });

  // Scroll to charts
  document.getElementById("section-charts").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Chart options helper ─────────────────────────────────────────────────────
function chartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#8892a4", boxWidth: 14 } },
      tooltip: {
        backgroundColor: "#1a1d27",
        borderColor: "#2e3248",
        borderWidth: 1,
        titleColor: "#e2e8f0",
        bodyColor: "#8892a4",
      },
    },
    scales: {
      x: { ticks: { color: "#8892a4" }, grid: { color: "rgba(255,255,255,.04)" } },
      y: {
        ticks: { color: "#8892a4" },
        grid: { color: "rgba(255,255,255,.04)" },
        title: { display: true, text: yLabel, color: "#8892a4" },
      },
    },
  };
}

// ── UI helpers ───────────────────────────────────────────────────────────────
function showLoading(show) {
  document.getElementById("loading").classList.toggle("hidden", !show);
}
function showError(msg) {
  const el = document.getElementById("error-msg");
  el.textContent = "❌ " + msg;
  el.classList.remove("hidden");
}
function hideError() {
  document.getElementById("error-msg").classList.add("hidden");
}
