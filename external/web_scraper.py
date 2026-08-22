"""Web Scraper — General-purpose web content extraction.

Fetches web pages and extracts readable content.
"""
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError

logger = logging.getLogger("external.web_scraper")


@dataclass
class ScrapedPage:
    """Scraped web page content."""
    url: str = ""
    title: str = ""
    text: str = ""
    links: list = None
    status_code: int = 0
    fetch_ms: float = 0.0
    size_bytes: int = 0

    def __post_init__(self):
        if self.links is None:
            self.links = []


class WebScraper:
    """Fetch and extract content from web pages."""

    def __init__(self, timeout: int = 15):
        self._timeout = timeout
        self._cache: dict[str, ScrapedPage] = {}
        self._cache_ttl = 300

    def scrape(self, url: str) -> ScrapedPage:
        """Fetch and extract content from a URL."""
        cached = self._cache.get(url)
        if cached and (time.time() - cached.fetch_ms) < self._cache_ttl * 1000:
            return cached

        start = time.time()
        page = ScrapedPage(url=url)

        try:
            from core.http_pool import get_client
            client = get_client()
            if client is not None:
                resp = client.get(url, timeout=self._timeout)
                html = resp.text
                page.status_code = resp.status_code
            else:
                import urllib.request
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (JARVIS Bot)",
                    "Accept": "text/html,application/xhtml+xml",
                })
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                    page.status_code = resp.status
            page.size_bytes = len(html.encode())

            page.title = self._extract_title(html)
            page.text = self._extract_text(html)
            page.links = self._extract_links(html, url)[:50]

        except Exception as e:
            if isinstance(e, HTTPError):
                page.status_code = e.code
                logger.warning("Scrape HTTP error %d for %s", e.code, url)
            else:
                logger.warning("Scrape failed for %s: %s", url, e)

        page.fetch_ms = (time.time() - start) * 1000
        self._cache[url] = page
        return page

    def _extract_title(self, html: str) -> str:
        match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        return self._clean(match.group(1)) if match else ""

    def _extract_text(self, html: str) -> str:
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<[^>]+>', ' ', html)
        html = re.sub(r'&\w+;', ' ', html)
        html = re.sub(r'\s+', ' ', html).strip()
        return html[:5000]

    def _extract_links(self, html: str, base_url: str) -> list:
        links = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)
        return [link for link in links if link.startswith("http")][:50]

    def _clean(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '', text).strip()

    def get_stats(self) -> dict[str, Any]:
        return {"cached_pages": len(self._cache)}


_scraper_instance: WebScraper | None = None


def get_web_scraper() -> WebScraper:
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = WebScraper()
    return _scraper_instance
