/**
 * JARVIS MK-X — Chat Module
 * Streaming chat with virtual DOM recycling for performance.
 */

import { authHeaders } from "./auth.js";

const MAX_MESSAGES = 100;
let container = null;
let msgCount = 0;
let messages = []; // Ring buffer of {role, text, el}
let activeStreamController = null;
let activeAudio = null;

export function initChat(containerEl) {
  container = containerEl;
}

export function getMessageCount() { return msgCount; }

export function addMessage(role, text, opts = {}) {
  if (!container) return;
  msgCount++;

  // Remove placeholder on first message
  if (msgCount === 1) container.innerHTML = "";

  // Evict oldest if over limit
  if (messages.length >= MAX_MESSAGES) {
    const old = messages.shift();
    if (old.el && old.el.parentNode) old.el.parentNode.removeChild(old.el);
  }

  const div = document.createElement("div");
  div.className = "animate-fade-in p-2.5 rounded-lg text-[11px] leading-relaxed";

  if (role === "user") {
    div.classList.add("bg-jarvis-cyan/5", "border", "border-jarvis-cyan/15");
    div.innerHTML = `<span class="text-jarvis-cyan text-[9px] tracking-widest block mb-1">YOU</span><span class="text-gray-300">${escapeHtml(text)}</span>`;
  } else if (role === "ai") {
    div.classList.add("bg-jarvis-orange/5", "border", "border-jarvis-orange/15");
    if (opts.thinking) {
      div.innerHTML = `<span class="text-jarvis-orange text-[9px] tracking-widest block mb-1">JARVIS</span><span class="text-gray-500 italic">${escapeHtml(text)}</span>`;
    } else {
      div.innerHTML = `<span class="text-jarvis-orange text-[9px] tracking-widest block mb-1">JARVIS</span><span class="text-gray-300">${escapeHtml(text)}</span>`;
    }
  } else {
    div.classList.add("bg-gray-800/30", "border", "border-gray-700/30");
    div.innerHTML = `<span class="text-gray-500 text-[9px]">${escapeHtml(text)}</span>`;
  }

  container.appendChild(div);
  messages.push({ role, text, el: div });
  container.scrollTop = container.scrollHeight;

  return div;
}

export function createStreamingMessage() {
  if (!container) return null;
  if (msgCount === 0) container.innerHTML = "";
  msgCount++;

  const div = document.createElement("div");
  div.className = "animate-fade-in p-2.5 rounded-lg text-[11px] leading-relaxed bg-jarvis-orange/5 border border-jarvis-orange/15";
  div.innerHTML = `<span class="text-jarvis-orange text-[9px] tracking-widest block mb-1">JARVIS</span><span class="text-gray-300 streaming-text"></span><div class="thinking-indicator"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div><div class="timing-bar"></div>`;

  container.appendChild(div);
  messages.push({ role: "ai", text: "", el: div });
  container.scrollTop = container.scrollHeight;

  return {
    el: div,
    streamSpan: div.querySelector(".streaming-text"),
    thinkingIndicator: div.querySelector(".thinking-indicator"),
    timingBar: div.querySelector(".timing-bar"),
  };
}

export function sendCommand(text, onToken, onTiming, onDone, onError) {
  if (!text) return;

  // Abort previous
  if (activeStreamController) { activeStreamController.abort(); activeStreamController = null; }

  addMessage("user", text);
  const stream = createStreamingMessage();
  if (!stream) return;

  let fullResponse = "";
  let tokenBuffer = "";
  let renderTimer = null;
  let firstToken = false;
  const RENDER_INTERVAL = 50;
  let audioQueue = [];
  let audioPlaying = false;

  function flushBuffer() {
    if (tokenBuffer) {
      fullResponse += tokenBuffer;
      tokenBuffer = "";
      stream.streamSpan.textContent = fullResponse;
      container.scrollTop = container.scrollHeight;
    }
    renderTimer = null;
  }

  function playNextAudio() {
    if (audioQueue.length === 0) { audioPlaying = false; return; }
    audioPlaying = true;
    const b64 = audioQueue.shift();
    try {
      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); playNextAudio(); };
      audio.onerror = () => { URL.revokeObjectURL(url); playNextAudio(); };
      activeAudio = audio;
      audio.play().catch(() => playNextAudio());
    } catch { playNextAudio(); }
  }

  activeStreamController = new AbortController();

  fetch("/api/chat/stream", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ text }),
    signal: activeStreamController.signal,
  }).then(response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) return;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.type === "text" && msg.token) {
              if (!firstToken) {
                firstToken = true;
                stream.thinkingIndicator.style.display = "none";
                stream.streamSpan.classList.remove("streaming-text");
                fullResponse += msg.token;
                stream.streamSpan.textContent = fullResponse;
                container.scrollTop = container.scrollHeight;
              } else {
                tokenBuffer += msg.token;
                if (!renderTimer) renderTimer = setTimeout(flushBuffer, RENDER_INTERVAL);
              }
            } else if (msg.type === "tts_chunk" && msg.audio) {
              audioQueue.push(msg.audio);
              if (!audioPlaying) playNextAudio();
            } else if (msg.type === "timing" && msg.timing) {
              onTiming?.(msg.timing);
              if (stream.timingBar) {
                const t = msg.timing;
                const parts = [];
                if (t.intent_ms) parts.push(`Intent: ${t.intent_ms}ms`);
                if (t.ttft_ms) parts.push(`TTFT: ${t.ttft_ms}ms`);
                if (t.tokens_per_sec) parts.push(`${t.tokens_per_sec} tok/s`);
                if (t.total_ms) parts.push(`Total: ${t.total_ms}ms`);
                if (t.provider) parts.push(t.provider);
                stream.timingBar.textContent = parts.join(" | ");
                stream.timingBar.classList.add("visible");
              }
            } else if (msg.type === "error") {
              stream.streamSpan.textContent = "Error: " + msg.error;
              stream.streamSpan.classList.add("text-red-400");
              stream.thinkingIndicator.style.display = "none";
              onError?.(msg.error);
            } else if (msg.type === "done") {
              if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
              flushBuffer();
              onDone?.();
            }
          } catch {}
        }
        read();
      });
    }
    read();
  }).catch(e => {
    if (e.name === "AbortError") {
      stream.streamSpan.textContent += " [cancelled]";
      stream.streamSpan.classList.add("text-gray-500");
    } else {
      stream.streamSpan.textContent = "Connection error: " + e.message;
      stream.streamSpan.classList.add("text-red-400");
    }
    stream.thinkingIndicator.style.display = "none";
    onError?.(e.message);
  });
}

export function speakText(text) {
  if (!text) return;
  if (activeAudio) { activeAudio.pause(); activeAudio = null; }

  fetch("/api/tts/stream", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ text }),
  }).then(response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let audioQueue = [];
    let playing = false;

    function playNext() {
      if (audioQueue.length === 0) { playing = false; return; }
      playing = true;
      const b64 = audioQueue.shift();
      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); playNext(); };
      audio.onerror = () => { URL.revokeObjectURL(url); playNext(); };
      activeAudio = audio;
      audio.play().catch(() => playNext());
    }

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) return;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.type === "tts_chunk" && msg.audio) {
              audioQueue.push(msg.audio);
              if (!playing) playNext();
            } else if (msg.type === "tts_done" && !playing && msg.audio) {
              const bytes = Uint8Array.from(atob(msg.audio), c => c.charCodeAt(0));
              const blob = new Blob([bytes], { type: "audio/wav" });
              const url = URL.createObjectURL(blob);
              activeAudio = new Audio(url);
              activeAudio.onended = () => { URL.revokeObjectURL(url); activeAudio = null; };
              activeAudio.play().catch(() => {});
            }
          } catch {}
        }
        read();
      });
    }
    read();
  }).catch(() => {
    // Fallback: use old /api/tts endpoint
    fetch("/api/tts", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ text }),
    }).then(r => r.blob()).then(blob => {
      const url = URL.createObjectURL(blob);
      activeAudio = new Audio(url);
      activeAudio.onended = () => { URL.revokeObjectURL(url); activeAudio = null; };
      activeAudio.play().catch(() => {});
    }).catch(() => {});
  });
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
