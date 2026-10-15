/* IPC sender guard — the single trust boundary for Orbit's privileged channels.
 *
 * Every `ipcMain.handle` / `ipcMain.on` channel in main.js is a capability
 * that reaches past the renderer: filesystem tools, shell.openExternal,
 * downloads, permission mutation, window control, session partitioning.
 * Electron's security guidance is explicit that argument validation is not
 * enough — the *sender* must be validated too, because any webContents that
 * can reach `ipcRenderer` can invoke any channel.
 *
 * Orbit has exactly one window, so the allow-list is small and auditable:
 *
 *   1. the Orbit chrome renderer (mainWindow.webContents)
 *   2. its DevTools, so debugging still works
 *   3. any webContents we registered as a tab guest
 *
 * Everything else is rejected. Fail closed: an unknown sender gets no
 * capability, and the rejection is logged so a broken legitimate path is
 * diagnosable rather than silent.
 *
 * Kept dependency-free and free of `electron` imports so it can be unit
 * tested under plain `node` — the main process cannot be launched in CI here.
 */

"use strict";

/** Channels that may be called before a window reference exists. */
const BOOTSTRAP_CHANNELS = new Set(["orbit:get-bridge-token"]);

/**
 * Decide whether `event` came from a webContents Orbit trusts.
 *
 * `allowBootstrap` is deliberately NOT a blanket exemption. It only covers the
 * one case where refusing is worse than allowing: the main window reference is
 * not stored yet. It must never let an *unknown* sender through, because the
 * one bootstrap channel hands out the bridge token -- the secret that
 * authenticates every JARVIS browser call. Treating it as "no capability of
 * its own" is exactly backwards, and doing so is how a second window ends up
 * holding a privileged token.
 *
 * @param {{sender?: {id: number}}} event           Electron IPC event.
 * @param {{mainWebContents?: object|null, guestIds?: Iterable<number>,
 *          chromeIds?: Iterable<number>, allowBootstrap?: boolean,
 *          isDevTools?: boolean}} ctx
 * @returns {{ok: true} | {ok: false, reason: string}}
 */
function classifySender(event, ctx) {
  const sender = event && event.sender;
  if (!sender || typeof sender.id !== "number") {
    return { ok: false, reason: "no sender" };
  }

  const mainWebContents = ctx && ctx.mainWebContents;
  if (mainWebContents && sender === mainWebContents) {
    return { ok: true };
  }

  // Every Orbit chrome renderer, not just the most recently created one.
  // createWindow() reassigns mainWindow, so a second window (Ctrl+N, private)
  // would otherwise lock the first one out of every privileged channel.
  const chromeIds = (ctx && ctx.chromeIds) || [];
  for (const id of chromeIds) {
    if (sender.id === id) return { ok: true };
  }

  // DevTools attached to the main window is the same trust principal as the
  // window it inspects -- otherwise debugging breaks the app it debugs.
  if (ctx && ctx.isDevTools && mainWebContents &&
      sender === mainWebContents.devToolsWebContents) {
    return { ok: true };
  }

  // Registered tab guests. Compared by webContents.id, which is stable for
  // the lifetime of the guest, rather than by object identity.
  const guestIds = (ctx && ctx.guestIds) || [];
  for (const id of guestIds) {
    if (sender.id === id) return { ok: true };
  }

  // Only now, with every real trust check exhausted, consider the bootstrap
  // exemption -- and only because there is no window to compare against yet.
  if ((mainWebContents === null || mainWebContents === undefined) &&
      ctx && ctx.allowBootstrap) {
    return { ok: true };
  }

  if (mainWebContents === null || mainWebContents === undefined) {
    return { ok: false, reason: "no window yet" };
  }

  return { ok: false, reason: `untrusted webContents id=${sender.id}` };
}

/**
 * Wrap a handler so an untrusted sender never reaches it.
 *
 * @param {(event: object, ...args: any[]) => any} fn
 * @param {() => object} getContext  Called per message so window/guest
 *                                   changes are picked up without re-wiring.
 * @param {(reason: string) => void} onReject
 */
function guardHandler(fn, getContext, onReject) {
  return async (event, ...rest) => {
    const verdict = classifySender(event, getContext());
    if (!verdict.ok) {
      onReject(verdict.reason);
      // Throwing (rather than returning) keeps the renderer's existing
      // .catch() failure contract: a rejected call must not look successful.
      throw new Error(`IPC rejected: untrusted sender (${verdict.reason})`);
    }
    return fn(event, ...rest);
  };
}

/**
 * Wrap a fire-and-forget listener. Listeners return nothing, so an
 * untrusted sender is dropped and logged instead of throwing — throwing here
 * would surface as an unhandled error in the sender, which is exactly the
 * untrusted party we are defending against.
 */
function guardListener(fn, getContext, onReject) {
  return (event, ...rest) => {
    const verdict = classifySender(event, getContext());
    if (!verdict.ok) {
      onReject(verdict.reason);
      return;
    }
    return fn(event, ...rest);
  };
}

module.exports = { classifySender, guardHandler, guardListener, BOOTSTRAP_CHANNELS };