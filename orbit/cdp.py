"""JARVIS Orbit — CDP transport + CDPBackend over the DevTools protocol.

This is the locked control surface:
    browser tools -> BrowserController -> CDPBackend -> Chromium (CDP)

Direct CDP over the Chrome DevTools WebSocket (via ``websockets``) — the
engine-agnostic control path. It is intentionally NOT Playwright-specific and
NOT chrome.debugger (no extension-side control). The ``CDPConnection`` is a
thread-safe request/response + event wrapper; ``CDPBackend`` implements the
``BrowserBackend`` contract (reused from ``jbrowser.backend.base``) so the
existing BrowserController + tool handlers plug in unchanged.

Everything here reuses canonical JARVIS subsystems:
  navigation policy   -> jbrowser.network.BrowserNetworkPolicy
  tab identities      -> jbrowser.tabs  (stable uuid tab ids)
  event emission      -> jbrowser.events (browser.* bus events)
  ownership           -> TargetRegistry (orbit.registry) over core.locks
"""

from __future__ import annotations

import base64
import json
import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from websockets.sync.client import connect as ws_connect

from core.locks import OWNER_SYSTEM, OWNER_USER, ResourceLockedError, get_resource_lock
from jbrowser.backend.base import BrowserBackend, TabInfo
from jbrowser.events import (
    ACTION_COMPLETED,
    AGENT_ACTION,
    NAVIGATION_COMPLETED,
    NAVIGATION_STARTED,
    PAGE_LOADED,
    TAB_ACTIVATED,
    TAB_CLOSED,
    TAB_CREATED,
    emit_browser_event,
)
from jbrowser.network import BrowserNetworkPolicy, NetworkPolicyError
from jbrowser.tabs import TabManager
from orbit.registry import OWNER_AGENT, OrbitTarget, TargetRegistry

logger = logging.getLogger("orbit.cdp")

DEFAULT_CHROMIUM = "J_BROWSER_CHROMIUM_PATH"
_EXT_PATTERN = "/src/background/service-worker.js"


def _find_chromium() -> Path | None:
    """Resolve the unbranded Chromium runtime (never the user's installed Chrome).

    Resolution order:
      1. J_BROWSER_CHROMIUM_PATH env (explicit override)
      2. Playwright build under %LOCALAPPDATA%\\ms-playwright (dev/CI default)
    Returns None when nothing is resolvable (caller may inject).
    """
    env = os.environ.get(DEFAULT_CHROMIUM)
    if env and Path(env).exists():
        return Path(env)
    local = Path(os.environ.get("LOCALAPPDATA", "")) or Path.home() / "AppData" / "Local"
    local = local / "ms-playwright" if (local / "ms-playwright").exists() else local
    if (local / "ms-playwright").exists():
        local = local / "ms-playwright"
        found = sorted(local.glob("chromium-*/chrome-win64/chrome.exe"), reverse=True)
        if found:
            return found[0]
    return None


class CDPError(RuntimeError):
    """Raised when a CDP command returns an error."""


class CDPConnection:
    """Thread-safe request/response + event client over a DevTools WebSocket.

    A background reader thread routes CDP responses to the pending caller and
    buffers ``method`` events so ``wait_for_event`` can observe page lifecycle.
    """

    READER_STOP = "__stop__"

    def __init__(self, ws_url: str, timeout: float = 20.0) -> None:
        self._ws_url = ws_url
        self._timeout = timeout
        self._ws = ws_connect(ws_url, timeout=timeout)
        self._send_lock = threading.Lock()
        self._pending: dict[int, "list[dict]"] = {}
        self._events: list[dict] = []
        self._events_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._closed = False
        self._id = 0
        self._start_reader()

    def _start_reader(self) -> None:
        def _loop():
            while not self._closed:
                try:
                    raw = self._ws.recv()
                except Exception:
                    self._closed = True
                    for p in list(self._pending.values()):
                        for e in p:
                            e.set()
                    return
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "id" in msg and msg["id"] in self._pending:
                    with self._send_lock:
                        waiter = self._pending.pop(msg["id"], None)
                    if waiter:
                        waiter.append(msg)
                        waiter.set()
                elif "method" in msg:
                    with self._events_lock:
                        self._events.append(msg)

        self._reader = threading.Thread(target=_loop, daemon=True, name="cdp-reader")
        self._reader.start()

    def _next_id(self) -> int:
        with self._send_lock:
            self._id += 1
            return self._id

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send a CDP command and wait for its response."""
        if self._closed:
            raise CDPError(f"CDP connection closed for {method}")
        rid = self._next_id()
        waiter: list[dict] = []
        with self._send_lock:
            self._pending[rid] = waiter
        payload = json.dumps({"id": rid, "method": method, "params": params or {}})
        try:
            with self._send_lock:
                self._ws.send(payload)
        except Exception as e:
            self._pending.pop(rid, None)
            raise CDPError(f"CDP send {method} failed: {e}") from e
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            if waiter:
                msg = waiter[0]
                if "error" in msg:
                    err = msg["error"]
                    raise CDPError(f"CDP {method} error: {err.get('message', err)}")
                return msg.get("result", {})
            if self._closed:
                break
            time.sleep(0.005)
        self._pending.pop(rid, None)
        raise CDPError(f"CDP {method} timed out after {self._timeout:.0f}s")

    def events_since(self, marker: int) -> list[dict]:
        with self._events_lock:
            return list(self._events[marker:])

    def wait_for_event(self, method_prefix: str, *, timeout: float = 10.0,
                       predicate=None) -> dict | None:
        """Wait for an event whose ``method`` starts with ``method_prefix``."""
        start = time.time()
        while time.time() - start < timeout:
            with self._events_lock:
                for ev in self._events:
                    if ev["method"].startswith(method_prefix):
                        if predicate is None or predicate(ev.get("params", {})):
                            return ev
            if self._closed:
                return None
            time.sleep(0.02)
        return None

    def consume_events(self, method_prefix: str) -> list[dict]:
        """Drain and return buffered events matching ``method_prefix``."""
        with self._events_lock:
            kept, out = [], []
            for ev in self._events:
                if ev["method"].startswith(method_prefix):
                    out.append(ev)
                else:
                    kept.append(ev)
            self._events[:] = kept
        return out

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._ws.close()
        except Exception:
            pass

    def __enter__(self) -> "CDPConnection":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# JS helpers executed in-page (bounded observation; never a raw DOM dump).

_JS_PAGE_TEXT = (
    "(function(){"
    "var b=document.body;"
    "var t=b?b.innerText:'';"
    "return t.slice(0,20000);"
    "})()"
)

_JS_TITLE_URL = (
    "(function(){return JSON.stringify({url:location.href,title:document.title})})()"
)

_JS_CURRENT_EL = (
    "(function(){var els=Array.from(document.querySelectorAll("
    "'a[href],button,input,select,textarea,[role=button],[role=link],[role=textbox]'));"
    "var i=EL_INDEX;var el=els[i];if(!el)return JSON.stringify({ok:false});"
    "var r=el.getBoundingClientRect();"
    "return JSON.stringify({ok:true,tag:el.tagName,text:(el.innerText||'').slice(0,80),"
    "x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)});})()"
)

_JS_PAGE_READY = "(document.readyState||'complete')"


class CDPBackend(BrowserBackend):
    """A ``BrowserBackend`` implemented over direct CDP.

    ``CDPBackend`` launches/attaches to unbranded Chromium, enumerates page
    targets, maps them to stable JARVIS tab ids via :class:`TargetRegistry`,
    and drives navigation/reads/actions over CDP.
    """

    def __init__(
        self,
        *,
        chrome: str | Path | None = None,
        profile_dir: Path | None = None,
        headless: bool = False,
        cdp_port: int = 0,
        network_policy: BrowserNetworkPolicy | None = None,
        extension_dir: Path | None = None,
        timeout: float = 20.0,
        start_timeout: float = 25.0,
        auto_launch: bool = True,
    ) -> None:
        self._chrome = str(chrome) if chrome else None
        self._profile_dir = profile_dir
        self._headless = headless
        self._cdp_port = cdp_port
        self._network = network_policy or BrowserNetworkPolicy.default()
        self._extension_dir = extension_dir
        self._timeout = timeout
        self._start_timeout = start_timeout
        self._process: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._base = ""
        self._browser_conn: CDPConnection | None = None
        self._tabs = TabManager()
        self._registry = TargetRegistry(locks=get_resource_lock())
        self._pages: dict[str, CDPConnection] = {}   # tab_id -> page connection
        # CDP allows at most 1 session per target per websocket. We open one
        # browser-level websocket for Target.* and one page websocket per tab.
        self._session_of: dict[str, str] = {}
        self._launched = False
        self._started = False
        self._active: str | None = None
        self._auto_launch = auto_launch
        self._launch_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def _resolve_chrome(self) -> str:
        if self._chrome:
            return self._chrome
        found = _find_chromium()
        if found is None:
            raise RuntimeError(
                "no unbranded Chromium runtime resolvable; set "
                "J_BROWSER_CHROMIUM_PATH or run 'playwright install chromium'"
            )
        return str(found)

    def _pick_port(self) -> int:
        if self._cdp_port:
            return self._cdp_port
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def launch(self, launch_url: str = "about:blank") -> None:
        """Launch/attach Chromium. Idempotent."""
        with self._launch_lock:
            if self._started and self._base:
                return
            chrome = self._resolve_chrome()
            port = self._pick_port()
            self._profile_dir = self._profile_dir or Path("config/browser_profiles/orbit")
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                chrome,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={self._profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate",
            ]
            if self._headless:
                cmd.append("--headless=new")
            if self._extension_dir:
                cmd.append(f"--load-extension={self._extension_dir}")
            cmd.append(launch_url)
            logger.info("orbit cdp launch: port=%s headless=%s", port, self._headless)
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._base = f"http://127.0.0.1:{port}"
            self._wait_http(self._base)
            self._browser_conn = CDPConnection(self._version_ws(), timeout=self._timeout)
            self._launched = True
            self._started = True

    def _version_ws(self) -> str:
        import urllib.request
        with urllib.request.urlopen(self._base + "/json/version", timeout=5) as r:
            return json.loads(r.read().decode())["webSocketDebuggerUrl"]

    def _http_json(self, path: str, timeout: float = 5.0) -> list[dict] | dict:
        import urllib.request
        with urllib.request.urlopen(self._base + path, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def _wait_http(self, base: str, timeout: float | None = None) -> None:
        import urllib.request
        deadline = time.time() + (timeout or self._start_timeout)
        while time.time() < deadline:
            try:
                urllib.request.urlopen(base + "/json/version", timeout=2)
                return
            except Exception:
                time.sleep(0.25)
        raise CDPError(f"Chromium did not expose CDP at {base} within start timeout")

    @property
    def launched(self) -> bool:
        return self._launched

    @property
    def registry(self) -> TargetRegistry:
        return self._registry

    def create_session(self, session_id: str, *, persistent: bool = False) -> None:
        # Logical-only; sessions map 1:1 to the shared browser profile for now.
        if persistent:
            logger.info("orbit persistent session declared: %s", session_id)

    def close_session(self, session_id: str | None = None) -> None:
        target_ids = list(self._session_of.keys())
        if session_id is not None:
            target_ids = [t for t in target_ids if self._session_of.get(t) == session_id]
        for tab_id in target_ids:
            self.close_tab(tab_id)
        self._session_of.pop(session_id, None)

    def shutdown(self) -> None:
        """Release native resources (process + connections)."""
        for conn in list(self._pages.values()):
            conn.close()
        self._pages.clear()
        if self._browser_conn:
            self._browser_conn.close()
            self._browser_conn = None
        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except Exception:
                    self._process.kill()
            except Exception:
                pass
            self._process = None
        self._started = False
        self._launched = False

    def status(self) -> dict:
        return {
            "backend": "orbit-cdp",
            "available": self._started,
            "launched": self._launched,
            "headless": self._headless,
            "tabs": len(self._registry),
            "active_tab": self._registry.active().tab_id if self._registry.active() else None,
            "sessions": len(self._session_of),
            "network_policy": "default-deny-private",
            "owns": self._registry.status().get("owners", {}),
        }

    # ---------------------------------------------------------------- targets
    def browser_call(self, method: str, params: dict | None = None) -> dict:
        if self._browser_conn is None:
            raise CDPError("browser not launched")
        return self._browser_conn.call(method, params)

    def _target_ws(self, target_id: str) -> str:
        for t in self._http_json("/json"):
            if t.get("id") == target_id:
                return t.get("webSocketDebuggerUrl", "")
        return ""

    def _page_conn(self, tab_id: str) -> CDPConnection:
        conn = self._pages.get(tab_id)
        if conn is not None and not conn._closed:
            return conn
        t = self._registry.lookup(tab_id)
        if t is None:
            raise RuntimeError(f"tab not found: {tab_id}")
        ws = t.ws_url or self._target_ws(t.target_id)
        conn = CDPConnection(ws, timeout=self._timeout)
        self._pages[tab_id] = conn
        t.started_ws = True
        return conn

    def _resolve_page(self, tab_id: str | None) -> str:
        key = tab_id or self._active
        if key is None or self._registry.lookup(key) is None:
            raise RuntimeError("No active tab; open one with browser.new_tab first.")
        return key

    # ---------------------------------------------------------------- sessions/tabs
    def create_tab(self, session_id: str, url: str = "") -> TabInfo:
        self.launch()
        with self._proc_lock:
            res = self.browser_call("Target.createTarget", {
                "url": url or "about:blank",
                "newWindow": False,
                "background": False,
            })
            target_id = res["targetId"]
            t = self._registry.register(
                target_id, session_id, OWNER_SYSTEM,
                url=url, title="",
            )
            self._session_of[t.tab_id] = session_id
            self._registry.activate(t.tab_id)
            self._active = t.tab_id
            if t.tab_id in self._pages:
                self._pages[t.tab_id].close()
                del self._pages[t.tab_id]
            emit_browser_event(TAB_CREATED, {"tab_id": t.tab_id, "url": url},
                               session_id=session_id)
            return TabInfo(
                tab_id=t.tab_id, session_id=session_id, url=url or "about:blank",
                title="", active=True,
            )

    def close_tab(self, tab_id: str) -> bool:
        t = self._registry.lookup(tab_id)
        if t is None:
            return False
        try:
            self.browser_call("Target.closeTarget", {"targetId": t.target_id})
        except Exception:
            pass
        conn = self._pages.pop(tab_id, None)
        if conn:
            conn.close()
        emitted = self._session_of.pop(tab_id, None)
        self._registry.remove(tab_id)
        if self._active == tab_id:
            act = self._registry.active()
            self._active = act.tab_id if act else None
        emit_browser_event(TAB_CLOSED, {"tab_id": tab_id}, session_id=emitted or "")
        return True

    def list_tabs(self, session_id: str | None = None) -> list[TabInfo]:
        out = []
        for t in self._registry.list():
            if session_id is not None and t.session_id != session_id:
                continue
            out.append(TabInfo(
                tab_id=t.tab_id, session_id=t.session_id,
                url=t.url, title=t.title, active=t.active,
                created_at=t.created_at,
            ))
        return out

    def switch_tab(self, tab_id: str) -> TabInfo:
        t = self._registry.activate(tab_id)
        if t is None:
            raise KeyError(f"tab not found: {tab_id}")
        self._active = tab_id
        emit_browser_event(TAB_ACTIVATED, {"tab_id": tab_id}, session_id=t.session_id)
        return TabInfo(
            tab_id=t.tab_id, session_id=t.session_id, url=t.url,
            title=t.title, active=True, created_at=t.created_at,
        )

    def active_tab(self):
        t = self._registry.active()
        if t is None:
            return None
        return TabInfo(
            tab_id=t.tab_id, session_id=t.session_id, url=t.url,
            title=t.title, active=True, created_at=t.created_at,
        )

    # ------------------------------------------------------------- navigation
    def _normalize_url(self, url: str) -> str:
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def navigate(self, url: str, tab_id: str | None = None) -> TabInfo:
        key = self._resolve_page(tab_id)
        self.launch()
        target = self._normalize_url(url)
        t = self._registry.lookup(key)
        # Network governance BEFORE the navigation (never after).
        target = self._network.validate(target)
        emit_browser_event(NAVIGATION_STARTED, {"tab_id": key, "url": target},
                           session_id=t.session_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        conn.call("Page.enable", {})
        conn.call("Page.navigate", {"url": target})
        # Wait for load (best-effort; don't block the tool on slow networks long).
        for _ in range(int(self._timeout / 0.25)):
            try:
                ready = self._eval(conn, _JS_PAGE_READY)
                if ready and ready.get("result", {}).get("value") == "complete":
                    break
            except Exception:
                break
            time.sleep(0.25)
        t.url = target
        t.title = self._eval_title(conn)
        emit_browser_event(NAVIGATION_COMPLETED, {"tab_id": key, "url": target},
                           session_id=t.session_id)
        emit_browser_event(PAGE_LOADED, {"tab_id": key, "url": target, "title": t.title},
                           session_id=t.session_id)
        return TabInfo(tab_id=key, session_id=t.session_id, url=t.url, title=t.title, active=t.active)

    def _ensure_page_dom(self, conn: CDPConnection) -> None:
        """Make sure the page's DOM domain is enabled for interaction helpers."""
        try:
            conn.call("Runtime.enable", {})
            conn.call("DOM.enable", {})
        except Exception:
            pass

    def _eval(self, conn: CDPConnection, expression: str) -> dict:
        res = conn.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return res

    def _eval_title(self, conn: CDPConnection) -> str:
        try:
            res = self._eval(conn, _JS_TITLE_URL)
            val = res.get("result", {}).get("value", "{}")
            if isinstance(val, str):
                try:
                    obj = json.loads(val)
                    return str(obj.get("title", ""))
                except Exception:
                    return ""
            return str(val)
        except Exception:
            return ""

    def go_back(self, tab_id: str | None = None) -> None:
        conn = self._page_conn(self._resolve_page(tab_id))
        self._ensure_page_dom(conn)
        conn.call("Page.navigateToHistoryEntry",
                  {"entryId": self._history_entries(conn, -1)})

    def go_forward(self, tab_id: str | None = None) -> None:
        conn = self._page_conn(self._resolve_page(tab_id))
        self._ensure_page_dom(conn)
        conn.call("Page.navigateToHistoryEntry",
                  {"entryId": self._history_entries(conn, +1)})

    def _history_entries(self, conn: CDPConnection, offset: int) -> int:
        try:
            res = conn.call("Page.getNavigationHistory")
            entries = res.get("entries", [])
            idx = res.get("currentIndex", 0) + offset
            if 0 <= idx < len(entries):
                return entries[idx]["id"]
        except Exception:
            pass
        raise CDPError("no history entry available")

    def reload(self, tab_id: str | None = None) -> None:
        conn = self._page_conn(self._resolve_page(tab_id))
        self._ensure_page_dom(conn)
        conn.call("Page.reload", {"ignoreCache": False})

    # ----------------------------------------------------------- read/observe
    def get_url(self, tab_id: str | None = None) -> str:
        key = self._resolve_page(tab_id)
        t = self._registry.lookup(key)
        try:
            res = self._eval(self._page_conn(key), _JS_TITLE_URL)
            val = res.get("result", {}).get("value", "{}")
            if isinstance(val, str):
                obj = json.loads(val)
                t.url = obj.get("url", t.url)
        except Exception:
            pass
        return t.url

    def get_title(self, tab_id: str | None = None) -> str:
        key = self._resolve_page(tab_id)
        t = self._registry.lookup(key)
        conn = self._page_conn(key)
        title = self._eval_title(conn)
        t.title = title or t.title
        return t.title

    def get_page_text(self, tab_id: str | None = None) -> str:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        res = self._eval(conn, _JS_PAGE_TEXT)
        return str(res.get("result", {}).get("value", "") or "")

    def get_dom_snapshot(self, tab_id: str | None = None) -> dict:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        res = self._eval(conn, """
        (function(){
          var els = Array.from(document.querySelectorAll(
            'a[href],button,input,select,textarea,[role="button"],[role="link"],[role="textbox"],[contenteditable="true"]'));
          var links=[], interactives=[], forms=[];
          var seen = {};
          var vp = {w: window.innerWidth, h: window.innerHeight};
          els.forEach(function(el,idx){
            var isCef = el.tagName === 'A' && el.getAttribute('href') !== null;
            var kind = 'widget';
            if (el.tagName === 'A') kind='link'; else
            if (el.tagName === 'BUTTON') kind='button'; else
            if (el.tagName === 'INPUT') kind='input'; else
            if (el.tagName === 'SELECT') kind='select'; else
            if (el.tagName === 'TEXTAREA') kind='textarea';
            var r=el.getBoundingClientRect();
            var visible=!!(r.width&&r.height&&el.getClientRects().length);
            var label=(el.getAttribute('aria-label')||el.title||el.innerText||el.value||'').trim().slice(0,120);
            var href=el.getAttribute?el.getAttribute('href')||'':'';
            var handle='el'+idx;
            interactives.push({handle:handle,tag:el.tagName.toLowerCase(),kind:kind,label:label,text:label.slice(0,80),href:href,visible:visible});
            if(kind==='link'&&href&&!seen[href]){seen[href]=1;links.push(href);}
          });
          var formEls = Array.from(document.querySelectorAll('form'));
          formEls.forEach(function(f){
            forms.push({action:f.getAttribute('action')||location.href,method:(f.getAttribute('method')||'get')});
          });
          var visibleI = interactives.filter(function(x){return x.visible;}).slice(0,60);
          return JSON.stringify({
            url:location.href,title:document.title,
            interactives:visibleI,
            links:links.slice(0,200),
            forms:forms.slice(0,20),
            viewport:vp,
            total:els.length
          });
        })()
        """)
        val = res.get("result", {}).get("value", "{}")
        try:
            out = json.loads(val) if isinstance(val, str) else {}
        except Exception:
            out = {}
        if not isinstance(out.get("interactives"), list):
            out["interactives"] = []
        if not isinstance(out.get("links"), list):
            out["links"] = []
        if not isinstance(out.get("forms"), list):
            out["forms"] = []
        if not isinstance(out.get("viewport"), dict):
            out["viewport"] = {}
        return out

    def get_selector_text(self, selector: str | None = None,
                          tab_id: str | None = None) -> str:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        if selector:
            expr = (
                "(function(){var el=document.querySelector(%r);"
                "return el?el.innerText.slice(0,5000):'';})()" % selector
            )
        else:
            expr = _JS_PAGE_TEXT
        res = self._eval(conn, expr)
        return str(res.get("result", {}).get("value", "") or "")

    def screenshot(self, path: str | None = None, tab_id: str | None = None) -> str:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        res = conn.call("Page.captureScreenshot", {"format": "png"})
        data = res.get("data", "")
        if not path:
            import tempfile
            path = os.path.join(tempfile.gettempdir(),
                                f"orbit_{int(time.time()*1000)}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))
        return path

    # ------------------------------------------------------------------- act
    def _element_handle_expr(self, index: int) -> str:
        return _JS_CURRENT_EL.replace("EL_INDEX", str(index))

    def click(self, handle: str, tab_id: str | None = None) -> bool:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        idx = int(handle[len("el"):]) if handle.startswith("el") and handle[2:].isdigit() else -1
        if idx < 0:
            raise RuntimeError(f"invalid handle: {handle}")
        # Resolve the element in page and click via evaluate + DOM.
        ok = self._eval(conn, self._element_handle_expr(idx))
        val = ok.get("result", {}).get("value", {})
        if isinstance(val, str):
            import json as _j
            try:
                val = _j.loads(val)
            except Exception:
                val = {}
        if not val.get("ok"):
            raise RuntimeError(f"element not found: {handle}")
        # Click coordinates if visible, else fall back to element.click().
        expr = (
            "(function(){var els=Array.from(document.querySelectorAll("
            "'a[href],button,input,select,textarea,[role=button],[role=link],[role=textbox]'));"
            "var el=els[%d];if(!el)return false;"
            "el.scrollIntoView({block:'center'});el.click();return true;})()" % idx
        )
        res = self._eval(conn, expr)
        return bool(res.get("result", {}).get("value", False))

    def type_text(self, handle: str, text: str, tab_id: str | None = None) -> bool:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        idx = int(handle[len("el"):]) if handle.startswith("el") and handle[2:].isdigit() else -1
        if idx < 0:
            raise RuntimeError(f"invalid handle: {handle}")
        safe_text = json.dumps(text)
        expr = (
            "(function(){var els=Array.from(document.querySelectorAll("
            "'input,textarea,[role=textbox]'));var el=els[%d];if(!el)return false;"
            "el.focus();var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set||"
            "Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
            "setter?setter.call(el,%s):(el.value=%s);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));"
            "return true;})()" % (idx, safe_text, safe_text)
        )
        self._ensure_page_dom(conn)
        res = self._eval(conn, expr)
        return bool(res.get("result", {}).get("value", False))

    def click_selector(self, selector: str, tab_id: str | None = None) -> bool:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        expr = (
            "(function(){var el=document.querySelector(%r);"
            "if(!el)return false;el.scrollIntoView({block:'center'});el.click();return true;})()" % selector
        )
        res = self._eval(conn, expr)
        return bool(res.get("result", {}).get("value", False))

    def type_selector(self, selector: str, text: str, tab_id: str | None = None) -> bool:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        safe_text = json.dumps(text)
        expr = (
            "(function(){var el=document.querySelector(%r);if(!el)return false;"
            "el.focus();var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set||"
            "Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
            "setter?setter.call(el,%s):(el.value=%s);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));return true;})()"
            % (selector, safe_text, safe_text)
        )
        res = self._eval(conn, expr)
        return bool(res.get("result", {}).get("value", False))

    def scroll(self, direction: str, amount: int = 500, tab_id: str | None = None) -> None:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        if direction == "top":
            expr = "window.scrollTo(0,0)"
        elif direction == "bottom":
            expr = "window.scrollTo(0,document.body.scrollHeight)"
        elif direction == "up":
            expr = "window.scrollBy(0,-%d)" % amount
        elif direction == "down":
            expr = "window.scrollBy(0,%d)" % amount
        else:
            raise ValueError(f"direction must be up/down/top/bottom, got {direction}")
        self._eval(conn, expr)

    def execute_script(self, script: str, tab_id: str | None = None) -> str:
        key = self._resolve_page(tab_id)
        conn = self._page_conn(key)
        self._ensure_page_dom(conn)
        try:
            res = self._eval(conn, script)
            exc = res.get("exceptionDetails")
            if exc:
                return f"<error: {exc.get('text', 'js')}>"
            val = res.get("result", {}).get("value")
            return str(val) if val is not None else ""
        except Exception as exc:
            return f"<error: {exc}>"


__all__ = ["CDPBackend", "CDPConnection", "CDPError", "NetworkPolicyError",
           "ResourceLockedError", "OWNER_USER", "OWNER_AGENT", "OWNER_SYSTEM"]