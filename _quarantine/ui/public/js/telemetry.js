/**
 * JARVIS MK-X — SSE Telemetry
 * Server-Sent Events for real-time system stats. No HTTP polling.
 */

let eventSource = null;
let listeners = [];
let connected = false;
let lastData = null;

export function connectTelemetry() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/telemetry/stream");

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      lastData = data;
      if (!connected) {
        connected = true;
        notify("connection", true);
      }
      for (const fn of listeners) fn(data);
    } catch {}
  };

  eventSource.onerror = () => {
    if (connected) {
      connected = false;
      notify("connection", false);
    }
    // Auto-reconnect handled by EventSource
  };
}

export function disconnectTelemetry() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  connected = false;
}

export function onTelemetry(fn) {
  listeners.push(fn);
  return () => { listeners = listeners.filter(l => l !== fn); };
}

export function onConnectionChange(fn) {
  listeners.push((data) => {
    if (data.__connection !== undefined) fn(data.__connection);
  });
  // Immediate call with current state
  fn(connected);
}

export function isConnected() { return connected; }
export function getLastData() { return lastData; }

function notify(type, value) {
  // Inject connection status into telemetry flow
  if (type === "connection") {
    for (const fn of listeners) fn({ __connection: value });
  }
}
