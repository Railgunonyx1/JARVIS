/**
 * JARVIS MK-X — Main App Controller
 * Orchestrates all modules: reactor, telemetry, chat, voice.
 * Uses requestAnimationFrame for unified animation loop.
 */

import { initReactor, setReactorMode, setReactorCpu, pauseReactor, resumeReactor } from "./reactor.js";
import { connectTelemetry, onTelemetry } from "./telemetry.js";
import { initChat, addMessage, sendCommand, speakText } from "./chat.js";
import { initVoice, toggleMic, toggleCam, isMicActive, isCamActive } from "./voice.js";
import { setAuthToken, authHeaders } from "./auth.js";

// ── State ───────────────────────────────────────────────────────────────
const CIRC = 2 * Math.PI * 42;
const startTime = Date.now();
let apiConnected = false;
let lastTelemetry = null;

async function fetchAuthToken() {
  try {
    const r = await fetch("/api/auth/token");
    const d = await r.json();
    if (d.ok && d.token) setAuthToken(d.token);
  } catch {}
}

// ── DOM Helpers ─────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Init ────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Fetch auth token first
  await fetchAuthToken();

  // Canvas reactor
  initReactor($("reactor-canvas"));

  // SSE telemetry
  connectTelemetry();
  onTelemetry(handleTelemetry);

  // Chat
  initChat($("ai-history"));

  // Voice
  initVoice({
    onMicChange: updateMicUI,
    onCamChange: updateCamUI,
  });

  // Mic result handler (from voice module)
  window.addEventListener("jarvis:mic-result", (e) => {
    const data = e.detail;
    if (data.text && data.text !== "(no speech detected)" && data.text !== "(no audio captured)") {
      // User spoke — message already added by voice module
    }
    if (data.response) {
      addMessage("ai", data.response);
      speakText(data.response);
    }
  });

  // Clock
  updateClock();
  setInterval(updateClock, 1000);

  // Real event-driven logs (no synthetic random logs)
  addLog("SYS", "HUD initialized");
  addLog("API", "Connecting...");

  // Page Visibility API — pause reactor when tab is hidden
  document.addEventListener("visibilitychange", () => {
    document.hidden ? pauseReactor() : resumeReactor();
  });

  // API health check (single timer, not redundant)
  checkAPI();
  setInterval(checkAPI, 10000);

  // Wire up UI events
  setupEvents();
});

// ── Telemetry Handler ───────────────────────────────────────────────────
function handleTelemetry(data) {
  // Connection status
  if (data.__connection !== undefined) {
    const connected = data.__connection;
    if (connected !== apiConnected) {
      apiConnected = connected;
      $("ws-dot").className = connected ? "status-dot on" : "status-dot off";
      $("ws-label").textContent = connected ? "ONLINE" : "OFFLINE";
      $("ws-label").className = connected ? "text-jarvis-cyan" : "text-gray-400";
    }
    return;
  }

  lastTelemetry = data;

  // Update gauges
  updateGauge("cpu", data.cpu || 0);
  updateGauge("ram", data.ram || 0);
  updateGauge("gpu", data.gpu || 0);

  // Quick stats
  $("q-cpu").textContent = `${Math.round(data.cpu || 0)}%`;
  $("q-ram").textContent = `${Math.round(data.ram || 0)}%`;

  // Text values
  $("vram-text").textContent = `${(data.vram || 0).toFixed(1)}GB`;
  $("net-text").textContent = `${Math.round(data.network || 0)}MB`;
  $("reactor-temp").textContent = `TEMP ${data.temperature || "--"}°C`;

  // Update reactor CPU intensity
  setReactorCpu(data.cpu || 0);

  // Wire performance mode into reactor
  if (data.performance_mode) {
    $("perf-indicator").textContent = data.performance_mode.toUpperCase();
    setReactorMode(data.performance_mode);
  }
}

function updateGauge(id, value) {
  const ring = $(id + "-ring");
  const text = $(id + "-text");
  if (ring) {
    const offset = CIRC - (CIRC * value / 100);
    ring.style.strokeDashoffset = offset;
  }
  if (text) text.textContent = `${Math.round(value)}%`;
}

// ── API Health Check ────────────────────────────────────────────────────
function checkAPI() {
  fetch("/api/status").then(r => r.json()).then(data => {
    if (!apiConnected) {
      apiConnected = true;
      $("ws-dot").className = "status-dot on";
      $("ws-label").textContent = "ONLINE";
      $("ws-label").className = "text-jarvis-cyan";
      addLog("API", "Backend connected");
    }
  }).catch(() => {
    if (apiConnected) {
      apiConnected = false;
      $("ws-dot").className = "status-dot off";
      $("ws-label").textContent = "OFFLINE";
      $("ws-label").className = "text-gray-400";
      addLog("API", "Backend unreachable", "text-jarvis-orange");
    }
  });
}

// ── Clock ───────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  $("clock").textContent = now.toLocaleTimeString("en-US", { hour12: false });
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
  const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  const s = String(elapsed % 60).padStart(2, "0");
  $("q-uptime").textContent = `${h}:${m}:${s}`;
}

// ── Logs ────────────────────────────────────────────────────────────────
function addLog(tag, text, color) {
  const panel = $("log-panel");
  if (!panel) return;
  const div = document.createElement("div");
  div.className = "text-gray-500 animate-fade-in";
  const c = color || "text-jarvis-cyan";
  div.innerHTML = `[<span class="${c}">${tag}</span>] ${escapeHtml(text)}`;
  panel.appendChild(div);
  if (panel.children.length > 60) panel.removeChild(panel.firstChild);
  panel.scrollTop = panel.scrollHeight;
}

// ── UI Events ───────────────────────────────────────────────────────────
function setupEvents() {
  // Command input
  const cmdInput = $("cmd-input");
  cmdInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSendCommand();
    }
  });

  // Send button
  $("send-btn").addEventListener("click", doSendCommand);

  // Mic
  $("mic-btn").addEventListener("click", () => toggleMic());
  $("dock-mic").addEventListener("click", () => toggleMic());

  // Camera
  $("dock-cam").addEventListener("click", () => toggleCam());

  // Health
  $("dock-health").addEventListener("click", showHealth);
  $("close-health").addEventListener("click", () => $("health-modal").classList.add("hidden"));
  $("health-modal").addEventListener("click", (e) => {
    if (e.target === $("health-modal")) $("health-modal").classList.add("hidden");
  });

  // Memory
  $("dock-memory").addEventListener("click", () => {
    fetch("/api/chat", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ text: "/memory status" }),
    }).then(r => r.json()).then(data => {
      if (data.ok && data.response) addMessage("ai", data.response);
    }).catch(() => {});
    addLog("CMD", "/memory status");
  });

  // Logs
  $("dock-logs").addEventListener("click", () => {
    const panel = $("log-panel");
    if (panel) panel.scrollTop = 0;
    $("dock-logs").classList.add("active");
    setTimeout(() => $("dock-logs").classList.remove("active"), 1000);
  });

  // Shutdown
  $("dock-shutdown").addEventListener("click", () => $("shutdown-modal").classList.remove("hidden"));
  $("close-shutdown").addEventListener("click", () => $("shutdown-modal").classList.add("hidden"));
  $("cancel-shutdown").addEventListener("click", () => $("shutdown-modal").classList.add("hidden"));
  $("confirm-shutdown").addEventListener("click", () => {
    $("shutdown-modal").classList.add("hidden");
    fetch("/api/shutdown", { method: "POST", headers: authHeaders() }).catch(() => {});
    addLog("SYS", "Shutdown initiated", "text-red-400");
    addMessage("system", "JARVIS shutting down...");
  });
  $("shutdown-modal").addEventListener("click", (e) => {
    if (e.target === $("shutdown-modal")) $("shutdown-modal").classList.add("hidden");
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "m") { e.preventDefault(); toggleMic(); }
    if (e.ctrlKey && e.shiftKey && e.key === "C") { e.preventDefault(); toggleCam(); }
    if (e.key === "Escape") {
      $("health-modal").classList.add("hidden");
      $("shutdown-modal").classList.add("hidden");
    }
  });
}

function doSendCommand() {
  const input = $("cmd-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  addLog("CMD", text);
  sendCommand(text, null, null, () => addLog("AI", "Response complete"), null);
}

// ── UI Updates ──────────────────────────────────────────────────────────
function updateMicUI(active) {
  const micBtn = $("mic-btn");
  const micStatusTop = $("mic-status-top");
  const waveform = $("waveform");
  const dockMic = $("dock-mic");

  if (active) {
    micBtn.classList.add("mic-active");
    $("mic-icon").textContent = "\u23F9";
    micStatusTop.textContent = "MIC ON";
    micStatusTop.className = "text-jarvis-orange";
    waveform.classList.remove("hidden");
    dockMic.classList.add("active");
  } else {
    micBtn.classList.remove("mic-active");
    $("mic-icon").textContent = "\u269E";
    micStatusTop.textContent = "MIC OFF";
    micStatusTop.className = "text-gray-400";
    waveform.classList.add("hidden");
    dockMic.classList.remove("active");
  }
}

function updateCamUI(active) {
  const dockCam = $("dock-cam");
  const camStatusTop = $("cam-status-top");
  const camStatusText = $("cam-status-text");
  const camFps = $("cam-fps");

  if (active) {
    dockCam.classList.add("active");
    camStatusTop.textContent = "CAM ON";
    camStatusTop.className = "text-jarvis-orange";
    camStatusText.textContent = "ACTIVE";
    camStatusText.className = "text-jarvis-cyan";
    camFps.textContent = "2 FPS";
  } else {
    dockCam.classList.remove("active");
    camStatusTop.textContent = "CAM OFF";
    camStatusTop.className = "text-gray-400";
    camStatusText.textContent = "STANDBY";
    camStatusText.className = "text-gray-500";
    camFps.textContent = "-- FPS";
  }
}

async function showHealth() {
  $("health-modal").classList.remove("hidden");
  $("health-content").innerHTML = '<div class="text-gray-500 italic">Loading health data...</div>';

  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    if (data.report) {
      $("health-content").innerHTML = `<pre class="text-[11px] text-gray-300 whitespace-pre-wrap">${escapeHtml(data.report)}</pre>`;
    } else if (data.checks) {
      $("health-content").innerHTML = data.checks.map(c => {
        const icon = c.ok ? '<span class="text-jarvis-cyan">OK</span>' : '<span class="text-red-400">FAIL</span>';
        return `<div class="flex justify-between"><span class="text-gray-500">${escapeHtml(c.name)}</span><span>${icon} ${escapeHtml(c.message)}</span></div>`;
      }).join("");
    }
  } catch {
    $("health-content").innerHTML = '<div class="text-gray-500 italic">Health check unavailable</div>';
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
