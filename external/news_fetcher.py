"""News Fetcher — Aggregate news from multiple sources.

Uses RSS feeds and web scraping for news aggregation.
"""
import logging
import json
import time
import re
import urllib.request
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("external.news")


@dataclass
class NewsArticle:
    """A single news article."""
    title: str = ""
    url: str = ""
    summary: str = ""
    source: str = ""
    published: str = ""
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary[:200],
            "source": self.source,
            "published": self.published,
        }


class NewsFetcher:
    """Fetch and aggregate news from multiple sources."""

    DEFAULT_FEEDS = {
        "tech": "https://hnrss.org/newest?count=10",
        "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    }

    def __init__(self):
        self._feeds: Dict[str, str] = dict(self.DEFAULT_FEEDS)
        self._cache: Dict[str, List[NewsArticle]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 900  # 15 minutes

    def add_feed(self, category: str, url: str) -> None:
        self._feeds[category] = url

    def fetch(self, category: str = "tech", max_articles: int = 10) -> List[NewsArticle]:
        """Fetch news from a specific category."""
        # Check cache
        if category in self._cache:
            age = time.time() - self._cache_time.get(category, 0)
            if age < self._cache_ttl:
                return self._cache[category][:max_articles]

        url = self._feeds.get(category)
        if not url:
            return self._cache.get(category, [])[:max_articles]

        try:
            from core.http_pool import fetch
            content = fetch(url)
            if content is None:
                return self._cache.get(category, [])[:max_articles]

            articles = self._parse_rss(content, category)
            self._cache[category] = articles
            self._cache_time[category] = time.time()

            return articles[:max_articles]

        except Exception as e:
            logger.warning("News fetch failed for %s: %s", category, e)
            return self._cache.get(category, [])[:max_articles]

    def _parse_rss(self, xml_content: str, category: str) -> List[NewsArticle]:
        """Simple RSS parser (no external dependencies)."""
        articles = []
        items = re.findall(r'<item>(.*?)</item>', xml_content, re.DOTALL)

        for item in items[:20]:
            title = re.search(r'<title[^>]*>(.*?)</title>', item, re.DOTALL)
            link = re.search(r'<link[^>]*>(.*?)</link>', item, re.DOTALL)
            desc = re.search(r'<description[^>]*>(.*?)</description>', item, re.DOTALL)
            pub = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', item, re.DOTALL)

            article = NewsArticle(
                title=self._clean_html(title.group(1)) if title else "",
                url=link.group(1).strip() if link else "",
                summary=self._clean_html(desc.group(1))[:200] if desc else "",
                source=category,
                published=pub.group(1) if pub else "",
                category=category,
            )
            if article.title:
                articles.append(article)

        return articles

    def _clean_html(self, text: str) -> str:
        text = text.strip()
        if text.startswith("<![CDATA[") and text.endswith("]]>"):
            text = text[9:-3]
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&\w+;', ' ', text)
        return text.strip()

    def get_headlines(self, category: str = "tech", count: int = 5) -> List[str]:
        articles = self.fetch(category, max_articles=count)
        return [a.title for a in articles if a.title]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "feeds": list(self._feeds.keys()),
            "cached_categories": len(self._cache),
            "total_articles": sum(len(a) for a in self._cache.values()),
        }


_news_instance: Optional[NewsFetcher] = None


def get_news_fetcher() -> NewsFetcher:
    global _news_instance
    if _news_instance is None:
        _news_instance = NewsFetcher()
    return _news_instance
