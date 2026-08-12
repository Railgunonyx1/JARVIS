"""Browser Control — Playwright-based browser automation for JARVIS.

Actions: open, search, click, type, scroll, get_text, get_url, screenshot,
         back, forward, reload, close, new_tab, close_tab, smart_click, smart_type
"""

import asyncio
import concurrent.futures
import logging
import os
import platform
import subprocess
import threading
import webbrowser
from pathlib import Path

logger = logging.getLogger("jarvis.actions.browser_control")

_OS = platform.system()
_playwright_available = False

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    from playwright.async_api import async_playwright
    _playwright_available = True
except ImportError:
    logger.warning("playwright not installed. Run: pip install playwright && playwright install chromium")


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    if "." not in url:
        url = url + ".com"
    return "https://" + url


_SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q=",
    "bing": "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
}

_ALIASES = {
    "google chrome": "chrome", "google-chrome": "chrome",
    "microsoft edge": "edge", "ms edge": "edge", "msedge": "edge",
    "mozilla firefox": "firefox", "opera gx": "operagx",
}


def _real_profile_dir(browser: str) -> str:
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam = os.environ.get("APPDATA", "")

    if _OS == "Windows":
        candidates = {
            "chrome": [Path(local) / "Google" / "Chrome" / "User Data"],
            "edge": [Path(local) / "Microsoft" / "Edge" / "User Data"],
            "brave": [Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"],
        }
    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        candidates = {
            "chrome": [lib / "Google" / "Chrome"],
            "edge": [lib / "Microsoft Edge"],
        }
    else:
        cfg = home / ".config"
        candidates = {
            "chrome": [cfg / "google-chrome", cfg / "chromium"],
            "edge": [cfg / "microsoft-edge"],
        }

    for p in candidates.get(browser, []):
        if p.exists():
            return str(p)

    fallback = home / ".jarvis_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def _open_native(url: str, browser_name: str | None = None) -> str:
    url = _normalize_url(url) if url and url.strip() else ""
    if url == "about:blank":
        url = ""

    if _OS == "Windows":
        try:
            if url:
                os.startfile(url)
            elif browser_name:
                spec = {
                    "chrome": "chrome", "edge": "msedge",
                    "firefox": "firefox", "brave": "brave",
                }.get(browser_name, browser_name)
                subprocess.Popen([spec], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened in browser: {url}" if url else f"Opened {browser_name or 'default browser'}."
        except Exception:
            pass

    try:
        if webbrowser.open(url):
            return f"Opened in default browser: {url}"
    except Exception:
        pass
    return f"Could not open a browser for: {url}"


class _BrowserSession:
    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._pw = None
        self._context = None
        self._page = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        if not _playwright_available:
            return
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 30) -> str:
        if not self._loop:
            raise RuntimeError("Session not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self):
        if self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(5)
            except Exception:
                pass

    async def _async_close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = self._page = None

    async def _launch(self):
        if self._context is not None:
            return
        if not self._pw:
            raise RuntimeError("Playwright not available. Run: pip install playwright && playwright install chromium")

        profile = _real_profile_dir(self.browser_name)
        self._context = await self._pw.chromium.launch_persistent_context(
            profile,
            headless=False,
            no_viewport=True,
            timeout=25000,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        logger.info("Browser launched: %s", self.browser_name)

    async def _get_page(self):
        await self._launch()
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
        return self._page

    async def go_to(self, url: str) -> str:
        url = _normalize_url(url)
        page = await self._get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(0.3)
        except PlaywrightTimeout:
            pass
        except Exception as e:
            return f"Navigation error: {e}"
        return f"Opened: {page.url}"

    async def search(self, query: str, engine: str = "google") -> str:
        base = _SEARCH_ENGINES.get(engine.lower(), _SEARCH_ENGINES["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8000)
                return f"Clicked text: '{text}'"
            if selector:
                await page.click(selector, timeout=8000)
                return f"Clicked: {selector}"
            return "No selector or text provided."
        except PlaywrightTimeout:
            return "Element not found (timeout)."
        except Exception as e:
            return f"Click error: {e}"

    async def smart_click(self, description: str) -> str:
        page = await self._get_page()
        for role in ("button", "link", "searchbox", "textbox", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5000)
                    return f"Clicked ({role}): '{description}'"
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(timeout=5000),
            lambda: page.get_by_placeholder(description, exact=False).first.click(timeout=5000),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5000),
        ):
            try:
                await attempt()
                return f"Clicked: '{description}'"
            except Exception:
                pass
        return f"Could not find element: '{description}'"

    async def type_text(self, selector: str = None, text: str = "", clear_first: bool = True) -> str:
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=50)
            return "Text typed."
        except Exception as e:
            return f"Type error: {e}"

    async def smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label", page.get_by_label(description, exact=False)),
            ("role", page.get_by_role("textbox", name=description)),
            ("searchbox", page.get_by_role("searchbox")),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return f"Typed into ({method}): '{description}'"
            except Exception:
                continue
        return f"Could not find input: '{description}'"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll error: {e}"

    async def get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4000]
        except Exception as e:
            return f"Could not get page text: {e}"

    async def get_url(self) -> str:
        page = await self._get_page()
        return page.url

    async def press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Pressed: {key}"
        except Exception as e:
            return f"Key error: {e}"

    async def screenshot(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "jarvis_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def back(self) -> str:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10000)
            return f"Navigated back: {page.url}"
        except Exception as e:
            return f"Back error: {e}"

    async def forward(self) -> str:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10000)
            return f"Navigated forward: {page.url}"
        except Exception as e:
            return f"Forward error: {e}"

    async def reload(self) -> str:
        page = await self._get_page()
        try:
            await page.reload(timeout=15000)
            return f"Page reloaded: {page.url}"
        except Exception as e:
            return f"Reload error: {e}"

    async def new_tab(self, url: str = "") -> str:
        page = await self._get_page()
        new_page = await page.context.new_page()
        self._page = new_page
        if url:
            return await self.go_to(url)
        return "New tab opened."

    async def close_tab(self) -> str:
        page = self._page
        if page and not page.is_closed():
            ctx = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return "Tab closed."
        return "No active tab to close."


class _SessionRegistry:
    def __init__(self):
        self._sessions: dict[str, _BrowserSession] = {}
        self._active_browser: str = ""
        self._lock = threading.Lock()

    def get(self, browser_name: str | None = None) -> _BrowserSession:
        if not browser_name:
            browser_name = self._active_browser or "chrome"
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                logger.info("New browser session: %s", browser_name)
            self._active_browser = browser_name
            return self._sessions[browser_name]

    def close_all(self) -> str:
        with self._lock:
            names = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
        return "All browsers closed." + (f" ({', '.join(names)})" if names else "")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = []
            for name in self._sessions:
                marker = " (active)" if name == self._active_browser else ""
                lines.append(f"  - {name}{marker}")
            return "Open browsers:\n" + "\n".join(lines)


_registry = _SessionRegistry()


def browser_action(params: dict) -> str:
    action = params.get("action", "").lower().strip()
    browser = params.get("browser", "").strip() or None

    if not action:
        return "No browser action specified."

    if action == "open":
        url = params.get("url", "")
        if not url:
            return "No URL provided."
        return _open_native(url, browser)

    if action == "close_all":
        return _registry.close_all()

    if action == "list":
        return _registry.list_sessions()

    if not _playwright_available:
        return "Playwright not installed. Run: pip install playwright && playwright install chromium"

    if action in ("search", "go_to"):
        try:
            sess = _registry.get(browser)
            if action == "search":
                return sess.run(sess.search(params.get("query", ""), params.get("engine", "google")))
            else:
                return sess.run(sess.go_to(params.get("url", "")))
        except concurrent.futures.TimeoutError:
            return "Browser action timed out."
        except Exception as e:
            return f"Browser error: {e}"

    try:
        sess = _registry.get(browser)
    except Exception as e:
        return f"Could not start browser: {e}"

    try:
        if action in ("click", "smart_click"):
            if action == "smart_click":
                return sess.run(sess.smart_click(params.get("description", "")))
            return sess.run(sess.click(params.get("selector"), params.get("text")))

        elif action in ("type", "smart_type"):
            if action == "smart_type":
                return sess.run(sess.smart_type(params.get("description", ""), params.get("text", "")))
            return sess.run(sess.type_text(params.get("selector"), params.get("text", ""), params.get("clear_first", True)))

        elif action == "scroll":
            return sess.run(sess.scroll(params.get("direction", "down"), int(params.get("amount", 500))))

        elif action == "get_text":
            return sess.run(sess.get_text())

        elif action == "get_url":
            return sess.run(sess.get_url())

        elif action == "press":
            return sess.run(sess.press(params.get("key", "Enter")))

        elif action == "screenshot":
            return sess.run(sess.screenshot(params.get("path")))

        elif action == "back":
            return sess.run(sess.back())

        elif action == "forward":
            return sess.run(sess.forward())

        elif action == "reload":
            return sess.run(sess.reload())

        elif action == "new_tab":
            return sess.run(sess.new_tab(params.get("url", "")))

        elif action == "close_tab":
            return sess.run(sess.close_tab())

        else:
            return f"Unknown browser action: '{action}'"

    except concurrent.futures.TimeoutError:
        return f"Browser action '{action}' timed out."
    except Exception as e:
        return f"Browser error ({action}): {e}"
