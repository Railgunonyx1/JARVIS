(function () {
  "use strict";

  const CAPTURE_PAGE = "jb:capture-page";
  const SELECTION = "jb:selection";
  const PAGE_CONTEXT = "jb:page-context";

  function visibleText(max = 12000) {
    const clone = document.body ? document.body.cloneNode(true) : null;
    if (!clone) return "";
    for (const el of clone.querySelectorAll("script,style,noscript,svg,canvas,video,audio,iframe,[hidden],[aria-hidden='true']")) {
      el.remove();
    }
    let text = (clone.innerText || clone.textContent || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    if (text.length > max) text = text.slice(0, max) + "\n…[truncated]";
    return text;
  }

  function pageTitle() {
    return (
      document.title ||
      document.querySelector("meta[property='og:title']")?.content ||
      location.hostname
    );
  }

  function getSelection() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.toString().trim()) return "";
    return sel.toString().trim().slice(0, 8000);
  }

  function capture() {
    return {
      type: PAGE_CONTEXT,
      url: location.href,
      title: pageTitle(),
      text: visibleText(),
      selection: getSelection(),
      language: document.documentElement.lang || "",
      timestamp: Date.now(),
    };
  }

  function send(msg) {
    try {
      chrome.runtime.sendMessage(msg);
    } catch (_) {}
  }

  document.addEventListener("selectionchange", () => {
    const text = getSelection();
    if (text) {
      send({ type: SELECTION, text, url: location.href, title: pageTitle() });
    }
  });

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message && message.type === CAPTURE_PAGE) {
      sendResponse({ ok: true, context: capture() });
      return true;
    }
    return false;
  });
})();
