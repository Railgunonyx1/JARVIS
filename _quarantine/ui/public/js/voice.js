/**
 * JARVIS MK-X — Voice Module
 * Server-side mic recording (Python sounddevice) — no browser getUserMedia needed.
 * This avoids QWebEngineView crashes from browser mic permissions.
 */

import { authHeaders } from "./auth.js";

let micActive = false;
let camActive = false;
let camStream = null;
let onMicChange = null;
let onCamChange = null;

export function initVoice(opts = {}) {
  onMicChange = opts.onMicChange || (() => {});
  onCamChange = opts.onCamChange || (() => {});
}

export function isMicActive() { return micActive; }
export function isCamActive() { return camActive; }

export function toggleMic() {
  if (micActive) stopMic();
  else startMic();
}

export function toggleCam() {
  if (camActive) stopCam();
  else startCam();
}

function startMic() {
  fetch("/api/mic/start", { method: "POST", headers: authHeaders() })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        micActive = true;
        onMicChange(true);
      } else {
        console.warn("Mic unavailable:", data.error);
      }
    })
    .catch(err => console.error("Mic start failed:", err));
}

function stopMic() {
  micActive = false;
  onMicChange(false);

  fetch("/api/mic/stop", { method: "POST", headers: authHeaders() })
    .then(r => r.json())
    .then(data => {
      if (data.ok && data.text) {
        // Emit event for chat module
        window.dispatchEvent(new CustomEvent("jarvis:mic-result", { detail: data }));
      }
    })
    .catch(err => console.error("Mic stop failed:", err));
}

async function startCam() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    camStream = stream;
    const video = document.getElementById("cam-video");
    video.srcObject = stream;
    document.getElementById("cam-placeholder").style.display = "none";
    camActive = true;
    onCamChange(true);

    video.onloadedmetadata = () => {
      document.getElementById("cam-res").textContent = `RES: ${video.videoWidth}x${video.videoHeight}`;
    };
  } catch (e) {
    console.error("Camera access denied:", e);
  }
}

function stopCam() {
  camActive = false;
  if (camStream) {
    camStream.getTracks().forEach(t => t.stop());
    camStream = null;
  }
  const video = document.getElementById("cam-video");
  video.srcObject = null;
  document.getElementById("cam-placeholder").style.display = "flex";
  document.getElementById("cam-res").textContent = "RES: --";
  onCamChange(false);
}
