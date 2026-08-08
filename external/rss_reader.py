"""RSS Reader — Subscribe to and manage RSS feeds.

Provides feed management, article retrieval, and unread tracking.
"""
import logging
import time
import re
import json
import urllib.request
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("external.rss_reader")


@dataclass
class RSSFeed:
    """An RSS feed subscription."""
    name: str
    url: str
    category: str = "general"
    last_fetched: float = 0.0
    last_article_count: int = 0


@dataclass
class RSSArticle:
    """An article from an RSS feed."""
    title: str = ""
    url: str = ""
    summary: str = ""
    feed_name: str = ""
    published: str = ""
    is_read: bool = False


class RSSReader:
    """Subscribe to and manage RSS feeds."""

    def __init__(self):
        self._feeds: Dict[str, RSSFeed] = {}
        self._articles: Dict[str, List[RSSArticle]] = {}
        self._read_set: set = set()
        self._fetch_count = 0

    def add_feed(self, name: str, url: str, category: str = "general") -> None:
        self._feeds[name] = RSSFeed(name=name, url=url, category=category)

    def remove_feed(self, name: str) -> None:
        self._feeds.pop(name, None)
        self._articles.pop(name, None)

    def fetch_feed(self, name: str, max_articles: int = 20) -> List[RSSArticle]:
        feed = self._feeds.get(name)
        if not feed:
            return []

        try:
            from core.http_pool import fetch
            content = fetch(feed.url)
            if content is None:
                return self._articles.get(name, [])[:max_articles]

            articles = self._parse_feed(content, name, max_articles)
            self._articles[name] = articles
            feed.last_fetched = time.time()
            feed.last_article_count = len(articles)
            self._fetch_count += 1
            return articles

        except Exception as e:
            logger.warning("RSS fetch failed for %s: %s", name, e)
            return self._articles.get(name, [])

    def _parse_feed(self, xml: str, feed_name: str, max_items: int) -> List[RSSArticle]:
        articles = []
        items = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
        for item in items[:max_items]:
            title = re.search(r'<title[^>]*>(.*?)</title>', item, re.DOTALL)
            link = re.search(r'<link[^>]*>(.*?)</link>', item, re.DOTALL)
            desc = re.search(r'<description[^>]*>(.*?)</description>', item, re.DOTALL)
            pub = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', item, re.DOTALL)

            uid = f"{feed_name}:{title.group(1).strip()[:50] if title else ''}"
            articles.append(RSSArticle(
                title=self._clean(title.group(1)) if title else "",
                url=link.group(1).strip() if link else "",
                summary=self._clean(desc.group(1))[:200] if desc else "",
                feed_name=feed_name,
                published=pub.group(1) if pub else "",
                is_read=uid in self._read_set,
            ))
        return articles

    @staticmethod
    def _clean(text: str) -> str:
        text = text.strip()
        if text.startswith("<![CDATA[") and text.endswith("]]>"):
            text = text[9:-3]
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&\w+;', ' ', text)
        return text.strip()

    def get_all_articles(self, unread_only: bool = False) -> List[RSSArticle]:
        all_articles = []
        for articles in self._articles.values():
            all_articles.extend(articles)
        if unread_only:
            all_articles = [a for a in all_articles if not a.is_read]
        return sorted(all_articles, key=lambda a: a.published, reverse=True)

    def mark_read(self, title: str) -> None:
        self._read_set.add(title)

    def get_feeds(self) -> List[Dict[str, Any]]:
        return [{"name": f.name, "url": f.url, "category": f.category,
                 "last_fetched": f.last_fetched, "articles": f.last_article_count}
                for f in self._feeds.values()]

    def get_stats(self) -> Dict[str, Any]:
        total_articles = sum(len(a) for a in self._articles.values())
        unread = sum(1 for a in self.get_all_articles() if not a.is_read)
        return {
            "feeds": len(self._feeds),
            "total_articles": total_articles,
            "unread": unread,
            "fetch_count": self._fetch_count,
        }


_rss_instance: Optional[RSSReader] = None


def get_rss_reader() -> RSSReader:
    global _rss_instance
    if _rss_instance is None:
        _rss_instance = RSSReader()
    return _rss_instance
