/**
 * ui.js — Orbit's in-house UI primitives (shadcn/ui conventions, zero-build
 * vanilla stack). No dependencies; loads before every feature module.
 *
 * Exposes window.UI: cn, escapeHtml, Button, Popup (anchored popover with
 * menu semantics), Modal, Toast. Every component handles ARIA attributes,
 * Escape-to-close, focus restoration, and per-instance rate-limited error
 * logging.
 */
(function () {
  "use strict";

  // ── error log (per-component rate limit) ─────────────────────────
  const _logAt = Object.create(null);
  function logErr(what, err) {
    const now = Date.now();
    if (now - (_logAt[what] || 0) < 5000) return;
    _logAt[what] = now;
    try {
      if (window.ErrorLogger && typeof window.ErrorLogger.log === "function") {
        window.ErrorLogger.log("error", "[ui] " + what, String(err));
      } else if (window.console) {
        console.warn("[ui:" + what + "]", err);
      }
    } catch (_) { /* never throw from logging */ }
  }

  // ── cn(): class merge (clsx + tailwind-merge spirit, 10 lines) ───
  function cn() {
    let out = "";
    for (let i = 0; i < arguments.length; i++) {
      const a = arguments[i];
      if (!a) continue;
      if (typeof a === "string") out += (out ? " " : "") + a;
      else if (Array.isArray(a)) out += (out ? " " : "") + cn.apply(null, a);
      else if (typeof a === "object") {
        for (const k in a) if (Object.prototype.hasOwnProperty.call(a, k) && a[k]) out += (out ? " " : "") + k;
      }
    }
    return out;
  }

  // ── escapeHtml (single source of truth; re-exported globally) ────
  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // ── focus helpers ────────────────────────────────────────────────
  function focusables(container) {
    if (!container) return [];
    const sel = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return Array.prototype.filter.call(container.querySelectorAll(sel), function (el) {
      return el.offsetParent !== null || el === document.activeElement;
    });
  }

  function trapFocus(e, container) {
    if (e.key !== "Tab") return;
    const f = focusables(container);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // ── Button: element factory with variants ────────────────────────
  // UI.Button({ label, icon, variant, size, pressed, onClick, title })
  function Button(opts) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = cn("ui-btn",
      opts.variant && opts.variant !== "default" ? "ui-btn--" + opts.variant : "",
      opts.size && opts.size !== "default" ? "ui-btn--" + opts.size : "",
      opts.className);
    if (opts.title) { el.title = opts.title; el.setAttribute("aria-label", opts.title); }
    if (opts.icon) el.appendChild(document.createTextNode(opts.icon));
    if (opts.label) {
      const span = document.createElement("span");
      span.textContent = opts.label;
      el.appendChild(span);
    }
    if (opts.pressed !== undefined) {
      el.setAttribute("aria-pressed", String(!!opts.pressed));
    }
    if (opts.onClick) el.addEventListener("click", opts.onClick);
    return el;
  }

  // ── Popup: anchored popover with menu semantics ──────────────────
  // UI.Popup.open({ anchor, title, hint, width, items, onOpen, onClose })
  //   item: { type:"item", label, icon, sub, shortcut, checked, disabled, danger, onSelect }
  //         { type:"sep" }
  //   item: { type:"custom", el }
  // Returns { el, close }.
  const _openPopups = [];
  function closeTopPopup() { const p = _openPopups[_openPopups.length - 1]; if (p) p.close(); return _openPopups.length > 0; }

  document.addEventListener("keydown", function (e) {
    try {
      if (e.key === "Escape" && _openPopups.length) {
        e.stopPropagation();
        closeTopPopup();
      } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && _openPopups.length) {
        const top = _openPopups[_openPopups.length - 1];
        if (top && top.hasMenuItems) {
          e.preventDefault();
          const f = focusables(top.el).filter(function (el) { return !el.classList.contains("ui-menu-item") || !el.disabled; });
          if (f.length) {
            const i = f.indexOf(document.activeElement);
            if (i < 0) f[0].focus();
            else f[(i + (e.key === "ArrowDown" ? 1 : f.length - 1)) % f.length].focus();
          }
        }
      }
    } catch (err) { logErr("popup-keydown", err); }
  }, true);

  document.addEventListener("pointerdown", function (e) {
    try {
      for (let i = _openPopups.length - 1; i >= 0; i--) {
        const p = _openPopups[i];
        if (!p.el.contains(e.target) && !(p.anchor && p.anchor.contains(e.target))) p.close();
      }
    } catch (err) { logErr("popup-outside", err); }
  }, true);

  function Popup(opts) {
    const el = document.createElement("div");
    el.className = "ui-popup";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "false");
    if (opts.title) {
      el.setAttribute("aria-label", opts.title);
      const head = document.createElement("div");
      head.className = "ui-popup-header";
      const t = document.createElement("span");
      t.className = "ui-popup-title";
      t.textContent = opts.title;
      head.appendChild(t);
      if (opts.hint) {
        const h = document.createElement("span");
        h.className = "ui-popup-hint";
        h.textContent = opts.hint;
        head.appendChild(h);
      }
      el.appendChild(head);
    }

    const popup = { el: el, anchor: opts.anchor || null, hasMenuItems: false, close: close };
    const prevFocus = document.activeElement;

    function close() {
      const i = _openPopups.indexOf(popup);
      if (i >= 0) _openPopups.splice(i, 1);
      el.classList.remove("open");
      setTimeout(function () { try { el.remove(); } catch (_) {} }, 140);
      try { if (prevFocus && prevFocus.focus) prevFocus.focus({ preventScroll: true }); } catch (_) {}
      if (opts.onClose) { try { opts.onClose(); } catch (err) { logErr("popup-onclose", err); } }
    }

    // content
    let hasMenu = false;
    (opts.items || []).forEach(function (item) {
      try {
        if (!item) return;
        if (item.type === "sep") {
          const s = document.createElement("div");
          s.className = "ui-menu-sep";
          el.appendChild(s);
        } else if (item.type === "custom") {
          if (item.el) el.appendChild(item.el);
        } else {
          hasMenu = true;
          const b = document.createElement("button");
          b.type = "button";
          b.className = cn("ui-menu-item", item.danger && "ui-menu-item--danger");
          if (item.checked !== undefined) b.setAttribute("role", "menuitemradio");
          if (item.disabled) b.disabled = true;
          if (item.icon) {
            const ic = document.createElement("span");
            ic.className = "ui-menu-item-icon";
            ic.textContent = item.icon;
            b.appendChild(ic);
          }
          const lab = document.createElement("span");
          lab.className = "ui-menu-item-label";
          lab.textContent = item.label;
          b.appendChild(lab);
          if (item.sub) {
            const sub = document.createElement("span");
            sub.className = "ui-menu-item-sub";
            sub.textContent = item.sub;
            lab.appendChild(sub);
          }
          if (item.shortcut) {
            const sc = document.createElement("span");
            sc.className = "ui-menu-shortcut";
            sc.textContent = item.shortcut;
            b.appendChild(sc);
          }
          if (item.checked) {
            const chk = document.createElement("span");
            chk.className = "ui-menu-item-check";
            chk.textContent = "\u2713";
            b.appendChild(chk);
          }
          b.addEventListener("click", function () {
            if (item.disabled) return;
            close();
            if (item.onSelect) { try { item.onSelect(); } catch (err) { logErr("popup-select", err); } }
          });
          el.appendChild(b);
        }
      } catch (err) { logErr("popup-item", err); }
    });
    popup.hasMenuItems = hasMenu;
    if (hasMenu) el.setAttribute("role", "menu");

    document.body.appendChild(el);
    // position near anchor (or center-top fallback) — after attach, so
    // offsetWidth reflects the real rendered width
    if (opts.anchor && opts.anchor.getBoundingClientRect) {
      const r = opts.anchor.getBoundingClientRect();
      el.style.top = Math.round(r.bottom + 6) + "px";
      const w = Math.max(el.offsetWidth, opts.width || 0);
      el.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
      el.style.right = "auto";
    } else {
      el.style.top = "48px";
      el.style.right = "16px";
    }
    if (opts.width) el.style.minWidth = opts.width + "px";
    // next frame: activate transition + focus first item
    requestAnimationFrame(function () {
      try {
        el.classList.add("open");
        const f = focusables(el);
        if (f.length) f[0].focus({ preventScroll: true });
      } catch (err) { logErr("popup-open", err); }
    });
    _openPopups.push(popup);
    if (opts.onOpen) { try { opts.onOpen(popup); } catch (err) { logErr("popup-onopen", err); } }
    return popup;
  }

  // ── Modal: blocking dialog with focus trap ───────────────────────
  // UI.Modal.open({ title, description, body(el|node), actions:[{label,variant,onClick}], onClose })
  function Modal(opts) {
    const overlay = document.createElement("div");
    overlay.className = "ui-overlay";
    const modal = document.createElement("div");
    modal.className = "ui-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    if (opts.title) {
      modal.setAttribute("aria-label", opts.title);
      const t = document.createElement("div");
      t.className = "ui-modal-title";
      t.textContent = opts.title;
      modal.appendChild(t);
    }
    if (opts.description) {
      const d = document.createElement("div");
      d.className = "ui-modal-desc";
      d.textContent = opts.description;
      modal.appendChild(d);
    }
    const body = document.createElement("div");
    body.className = "ui-modal-body";
    if (typeof opts.body === "string") body.textContent = opts.body;
    else if (opts.body) body.appendChild(opts.body);
    modal.appendChild(body);

    const prevFocus = document.activeElement;
    function close() {
      overlay.classList.remove("open");
      document.removeEventListener("keydown", onKey, true);
      setTimeout(function () { try { overlay.remove(); } catch (_) {} }, 140);
      try { if (prevFocus && prevFocus.focus) prevFocus.focus({ preventScroll: true }); } catch (_) {}
      if (opts.onClose) { try { opts.onClose(); } catch (err) { logErr("modal-onclose", err); } }
    }
    function onKey(e) {
      try {
        if (e.key === "Escape") { e.stopPropagation(); close(); }
        else trapFocus(e, modal);
      } catch (err) { logErr("modal-key", err); }
    }

    if (opts.actions && opts.actions.length) {
      const row = document.createElement("div");
      row.className = "ui-modal-actions";
      opts.actions.forEach(function (a) {
        const b = Button({ label: a.label, variant: a.variant || "outline", onClick: function () { close(); if (a.onClick) { try { a.onClick(); } catch (err) { logErr("modal-action", err); } } } });
        row.appendChild(b);
      });
      modal.appendChild(row);
    }

    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    document.addEventListener("keydown", onKey, true);
    requestAnimationFrame(function () {
      try {
        overlay.classList.add("open");
        const f = focusables(modal);
        if (f.length) f[0].focus({ preventScroll: true });
      } catch (err) { logErr("modal-open", err); }
    });
    return { el: overlay, close: close };
  }

  // ── Toast: delegates to the existing core.showToast ──────────────
  function Toast(type, title, msg, dur) {
    try {
      if (typeof window.showToast === "function") window.showToast(type, title, msg, dur);
      else if (window.console) console.log("[toast]", type, title, msg || "");
    } catch (err) { logErr("toast", err); }
  }

  // ── View transitions (native View Transition API) ───────────────
  // Vanilla-DOM equivalent of React's <ViewTransition>: pass a function
  // that mutates the DOM in place and the swap animates as a cross-fade
  // on Chromium 111+ (this Electron renderer). Unsupported browsers and
  // prefers-reduced-motion users get the instant swap, unchanged.
  // `orbit-content` is our namespace so guest/extension transitions
  // can never collide with ours (see the CSS side in ui.css).
  function viewTransition(updateFn) {
    var reduce = false;
    try { reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (_) {}
    var safeFn = (typeof window.safe === "function") ? window.safe(updateFn, "viewTransition") : updateFn;
    if (reduce || typeof document.startViewTransition !== "function") {
      safeFn();
      return;
    }
    try { document.startViewTransition(safeFn); }
    catch (_) { safeFn(); }
  }

  // ── exports ──────────────────────────────────────────────────────
  window.UI = { cn: cn, escapeHtml: escapeHtml, Button: Button, Popup: Popup, Modal: Modal, Toast: Toast, viewTransition: viewTransition };
  // escapeHtml becomes globally available here (before settings-ux.js loads),
  // so the de-facto global contract is satisfied from first paint.
  if (typeof window.escapeHtml !== "function") window.escapeHtml = escapeHtml;
})();
