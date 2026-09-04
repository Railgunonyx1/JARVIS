import { BRIDGE } from "../lib/constants.js";

export class BridgeClient {
  constructor({ base = BRIDGE.base, timeoutMs = BRIDGE.connectTimeoutMs } = {}) {
    this.base = base;
    this.timeoutMs = timeoutMs;
    this._aborters = new Map();
  }

  async status() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.base}${BRIDGE.endpoints.status}`, {
        signal: controller.signal,
        cache: "no-store",
      });
      if (!res.ok) return { ok: false, kernel: "offline", http: res.status };
      return await res.json();
    } catch (_) {
      return { ok: false, kernel: "offline", error: "unreachable" };
    } finally {
      clearTimeout(timer);
    }
  }

  async chat({ sessionId, messages, page, onStart, onDelta, onDone, onError, signal }) {
    const controller = signal || new AbortController();
    this._aborters.set(sessionId, controller);
    let body;
    try {
      body = await fetch(`${this.base}${BRIDGE.endpoints.chat}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, messages, page }),
        signal: controller.signal,
        cache: "no-store",
      });
    } catch (e) {
      onError?.({ message: "bridge unreachable", code: "unreachable" });
      return;
    }
    if (!body.ok || !body.body) {
      let detail = "";
      try {
        detail = await body.text();
      } catch (_) {}
      onError?.({ message: `bridge http ${body.status}: ${detail.slice(0, 200)}`, code: "http" });
      return;
    }

    const reader = body.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const event = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          finished = this._handleSse(event, { onStart, onDelta, onDone, onError }) || finished;
          if (finished) break;
        }
        if (finished) break;
      }
      if (!finished) onDone?.();
    } catch (e) {
      if (e.name === "AbortError") {
        onError?.({ message: "aborted", code: "aborted" });
      } else {
        onError?.({ message: e?.message || "stream error", code: "stream" });
      }
    } finally {
      this._aborters.delete(sessionId);
    }
  }

  abort(sessionId) {
    const controller = this._aborters.get(sessionId);
    if (controller) controller.abort();
  }

  _handleSse(eventText, handlers) {
    const lines = eventText.split("\n");
    const dataLines = lines
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trim());
    if (dataLines.length === 0) return false;
    const data = dataLines.join("\n");
    let payload;
    try {
      payload = JSON.parse(data);
    } catch (_) {
      return false;
    }
    switch (payload.type) {
      case "start":
        handlers.onStart?.(payload);
        return false;
      case "delta":
        handlers.onDelta?.(payload.text || "");
        return false;
      case "done":
        handlers.onDone?.(payload);
        return true;
      case "error":
        handlers.onError?.({ message: payload.message, code: payload.code });
        return true;
    }
    return false;
  }
}
