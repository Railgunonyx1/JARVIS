import { Msg } from "./constants.js";

export function sendMessage(message) {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          reject(new Error(err.message));
          return;
        }
        resolve(response);
      });
    } catch (e) {
      reject(e);
    }
  });
}

export function onMessage(handler) {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    let handled = false;
    try {
      const outcome = handler(message, sender);
      if (outcome && typeof outcome.then === "function") {
        handled = true;
        outcome.then(
          (result) => sendResponse({ ok: true, result }),
          (error) => sendResponse({ ok: false, error: error?.message || String(error) })
        );
      } else if (outcome !== undefined && outcome !== null) {
        handled = true;
        sendResponse({ ok: true, result: outcome });
      }
    } catch (e) {
      handled = true;
      sendResponse({ ok: false, error: e?.message || String(e) });
    }
    if (!handled) {
      sendResponse(undefined);
    }
    return !!handled;
  });
}

export function broadcast(message) {
  try {
    chrome.runtime.sendMessage(message);
  } catch (_) {
    /* no listeners */
  }
}

export function broadcastType(type, payload) {
  broadcast({ type, payload });
}
