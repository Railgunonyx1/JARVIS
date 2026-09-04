// chrome.debugger (CDP) controller — privileged browser control layer.
//
// Chromium's remote debugging protocol exposed to extensions via
// chrome.debugger (works under Manifest V3; promises supported; attach by
// tabId, sendCommand by method, events routed by tabId via onEvent).
//
// SECURITY BOUNDARY (explicit, fail-closed):
//   * The "debugger" permission is declared but control is DISABLED until the
//     user explicitly opts in via chrome.storage (`controllerEnabled: true`).
//   * A "debuggee" is only attached after CONFIRM, which the caller must obtain
//     from the operator (sidebar / new-tab consent UI).
//   * Commands are classified SAFE vs PRIVILEGED. Untrusted/agent-originated
//     PRIVILEGED commands (click/type/navigate/evaluate/execution of page JS)
//     are rejected unless `consent === "approved"` was explicitly granted for
//     that individual command instance.
//   * Attach is mutually exclusive with user-opened DevTools for that tab; we
//     detach gracefully on onDetach.

import { BRIDGE } from "../lib/constants.js";

let attached = new Map(); // tabId -> { session, consented: Set<string> }

const PROTOCOL_VERSION = "1.3";

const PRIVILEGED_METHODS = new Set([
  "Runtime.evaluate",
  "Runtime.callFunctionOn",
  "Page.navigate",
  "Page.reload",
  "Input.dispatchMouseEvent",
  "Input.dispatchTouchEvent",
  "Input.insertText",
  "Input.dispatchKeyEvent",
  "DOM.getDocument",
  "DOM.querySelector",
  "DOM.requestNode",
]);

export async function isEnabled() {
  const { settings } = await chrome.storage.local.get("settings");
  return !!(settings && settings.controllerEnabled === true);
}

export async function setEnabled(enabled) {
  const { settings: cur = {} } = await chrome.storage.local.get("settings");
  await chrome.storage.local.set({ settings: { ...cur, controllerEnabled: !!enabled } });
  return !!enabled;
}

export function attachedTabs() {
  return Array.from(attached.keys());
}

export async function attach(tabId, { consent = false } = {}) {
  if (!(await isEnabled())) {
    return { ok: false, error: "controller disabled by user" };
  }
  if (!consent) {
    return { ok: false, error: "operator consent required before attach" };
  }
  try {
    await chrome.debugger.attach({ tabId }, PROTOCOL_VERSION);
    attached.set(tabId, { session: { tabId }, consented: new Set() });
    return { ok: true, tabId };
  } catch (e) {
    return { ok: false, error: e?.message || "attach failed" };
  }
}

export async function detach(tabId) {
  if (!attached.has(tabId)) return { ok: true };
  try {
    await chrome.debugger.detach({ tabId });
  } catch (_) {}
  attached.delete(tabId);
  return { ok: true };
}

export async function send(tabId, method, params = {}, { consent = false } = {}) {
  if (!attached.has(tabId)) {
    return { ok: false, error: "not attached" };
  }
  const entry = attached.get(tabId);
  if (PRIVILEGED_METHODS.has(method) && !consent && !entry.consented.has(method)) {
    return {
      ok: false,
      error: `privileged CDP method ${method} requires consent`,
      needsConsent: method,
    };
  }
  try {
    const result = await chrome.debugger.sendCommand({ tabId }, method, params);
    return { ok: true, result };
  } catch (e) {
    return { ok: false, error: e?.message || "command failed" };
  }
}

export async function evaluate(tabId, expression, { consent = false } = {}) {
  const res = await send(tabId, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  }, { consent });
  if (!res.ok) return res;
  if (res.result && res.result.exceptionDetails) {
    return { ok: false, error: res.result.exceptionDetails.text || "evaluation threw" };
  }
  return { ok: true, value: res.result && res.result.result ? res.result.result.value : undefined };
}

export async function navigate(tabId, url, { consent = false } = {}) {
  return send(tabId, "Page.navigate", { url }, { consent });
}

export function wireEvents() {
  chrome.debugger.onEvent.addListener((source, method, params) => {
    if (method === "Page.frameNavigated" || method === "Page.loadEventFired") {
      try {
        chrome.runtime.sendMessage({
          type: "jb:cdp-event",
          payload: { method, tabId: source.tabId, params },
        });
      } catch (_) {}
    }
  });
  chrome.debugger.onDetach.addListener((source) => {
    attached.delete(source.tabId);
  });
}

export function endpointForController() {
  return BRIDGE.endpoints.cdp;
}

wireEvents();
