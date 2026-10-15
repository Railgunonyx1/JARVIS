"""Tests for pass-11 tools: feed.read, reading.list, web.archive.

Hermetic: the pooled HTTP client (core.http_pool.fetch) is monkeypatched with
canned RSS/Atom/JSON Feed/HTML bodies, and ProjectContext is redirected into
tmp_path — no network, no real pages.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.http_pool  # noqa: E402
from tools import build_default_registry  # noqa: E402
from tools import feeds as fd  # noqa: E402
from tools import reading_list as rl  # noqa: E402
from tools import web_archive as wa  # noqa: E402


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(
        __import__("core.project", fromlist=["ProjectContext"]).ProjectContext,
        "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    return tmp_path


@pytest.fixture()
def http(monkeypatch):
    """Replace the pooled client with a canned URL -> body map."""
    responses: dict[str, str] = {}

    def _set(url, body):
        responses[url] = body

    def fake_fetch(url, timeout=10, **kwargs):
        if url not in responses:
            raise OSError(f"no canned response for {url}")
        return responses[url]

    monkeypatch.setattr(core.http_pool, "fetch", fake_fetch)
    return _set


# ---------------------------------------------------------------- registry

def test_pass11_tools_registered():
    registry = build_default_registry()
    for name in ("feed.read", "reading.list", "web.archive"):
        tool = registry.get(name)
        assert tool is not None, f"{name} missing"
        assert tool.handler is not None


# --------------------------------------------------------------- feed.read

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Example Blog</title>
<item><title>Post One</title><link>https://blog.example/post-one?utm_source=feed&amp;utm_medium=rss&amp;id=7</link>
<description>First post body</description><pubDate>Mon, 21 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Post Two</title><link>https://blog.example/post-two</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Example</title>
<entry><title>Entry One</title><link href="https://atom.example/e1?fbclid=xyz123"/>
<summary>Atom summary</summary><updated>2026-09-21T12:00:00Z</updated></entry>
</feed>"""

JSONFEED = json.dumps({
    "version": "https://jsonfeed.org/version/1.1",
    "items": [
        {"title": "JSON One", "url": "https://jf.example/1?utm_campaign=x&keep=1", "summary": "jf body"},
    ],
})


def test_feed_rss_with_tracking_stripped(workspace, http):
    http("https://feeds.example/blog.xml", RSS)
    res = fd.feed_read({"url": "https://feeds.example/blog.xml"})
    assert res.success
    assert "Post One" in res.output and "Post Two" in res.output
    assert "utm_source" not in res.output and "utm_medium" not in res.output
    assert "id=7" in res.output  # real params survive


def test_feed_atom(workspace, http):
    http("https://atom.example/feed", ATOM)
    res = fd.feed_read({"url": "https://atom.example/feed"})
    assert res.success and "Entry One" in res.output
    assert "fbclid" not in res.output


def test_feed_jsonfeed(workspace, http):
    http("https://jf.example/feed.json", JSONFEED)
    res = fd.feed_read({"url": "https://jf.example/feed.json"})
    assert res.success and "JSON One" in res.output
    assert "utm_campaign" not in res.output and "keep=1" in res.output


def test_feed_unseen_and_mark_seen(workspace, http):
    url = "https://feeds.example/blog.xml"
    http(url, RSS)
    first = fd.feed_read({"url": url, "unseen_only": True})
    assert "Post One" in first.output  # nothing marked yet → everything is new
    fd.feed_read({"url": url, "mark_seen": True})
    second = fd.feed_read({"url": url, "unseen_only": True})
    assert "No new items" in second.output
    # Feed gains an item → only the new one is reported.
    http(url, RSS.replace("</channel>", "<item><title>Post Three</title><link>https://blog.example/p3</link></item></channel>"))
    third = fd.feed_read({"url": url, "unseen_only": True})
    assert "Post Three" in third.output and "Post One" not in third.output


def test_feed_tolerates_bare_ampersands(workspace, http):
    """Real-world feeds ship invalid XML with bare '&'; Miniflux tolerates it."""
    dirty = '<?xml version="1.0"?><rss version="2.0"><channel><title>D</title><item><title>Q&amp;A post</title><link>https://d.example/q?a=1&b=2&utm_tag=z</link></item></channel></rss>'
    http("https://dirty.example/feed", dirty)
    res = fd.feed_read({"url": "https://dirty.example/feed"})
    assert res.success and "Q&A post" in res.output
    assert "utm_tag" not in res.output and "a=1&b=2" in res.output


def test_feed_errors(workspace, http):
    assert fd.feed_read({}).success is False
    assert fd.feed_read({"url": "ftp://x"}).success is False
    assert fd.feed_read({"url": "https://missing.example/feed"}).success is False
    http("https://notafeed.example/", "<html><body>hello</body></html>")
    res = fd.feed_read({"url": "https://notafeed.example/"})
    assert res.success is False and "no items parsed" in res.error


# ------------------------------------------------------------ reading.list

ARTICLE = """<html><head><title>Watcher Laws | Example</title></head><body>
<nav>Home About</nav>
<p>Watcher laws govern how autonomous agents may observe a page without
modifying it, and these rules were codified after long debate.</p>
<p>The second principle is data minimization: store only what the agent can
justify, and delete the rest on a schedule agreed with the user.</p>
<footer>copyright</footer></body></html>"""


def test_reading_list_save_read_remove(workspace, http):
    url = "https://news.example/watcher-laws"
    http(url, ARTICLE)
    saved = rl.reading_list({"action": "save", "url": url})
    assert saved.success and "Watcher Laws" in saved.output
    # duplicate refused
    assert rl.reading_list({"action": "save", "url": url}).success is False
    listed = rl.reading_list({"action": "list"})
    assert "Watcher Laws" in listed.output
    read = rl.reading_list({"action": "read", "url": url})
    assert "Watcher laws govern" in read.output
    assert rl.reading_list({"action": "remove", "url": url}).success is True
    assert "empty" in rl.reading_list({"action": "list"}).output.lower()


def test_reading_list_extracted_text_is_searchable(workspace, http):
    url = "https://news.example/data-minimization"
    http(url, ARTICLE)
    rl.reading_list({"action": "save", "url": url})
    from tools import doc_retrieval as dr

    res = dr.doc_search({"query": "data minimization"})
    assert res.success and "data-minimization" in res.output


def test_reading_list_save_offline_still_stores_url(workspace):
    res = rl.reading_list({"action": "save", "url": "https://unreachable.example/x"})
    assert res.success  # URL kept even when extraction fails
    read = rl.reading_list({"action": "read", "url": "https://unreachable.example/x"})
    assert "could not be extracted" in read.output


def test_reading_list_errors(workspace):
    assert rl.reading_list({"action": "save"}).success is False
    assert rl.reading_list({"action": "read", "url": "https://x.example/a"}).success is False


# ------------------------------------------------------------- web.archive

PAGE_V1 = "<html><title>Spec</title><p>Version one of the specification text, long enough to count as a paragraph.</p></html>"
PAGE_V2 = "<html><title>Spec</title><p>Version two changed the wording of the specification paragraph substantially.</p></html>"
URL = "https://specs.example/spec"


def test_archive_first_snapshot_then_dedup(workspace, http):
    http(URL, PAGE_V1)
    first = wa.web_archive({"url": URL})
    assert first.success and "Archived" in first.output
    again = wa.web_archive({"url": URL})
    assert again.success and "Unchanged" in again.output  # hash dedup
    # Content change → new snapshot.
    http(URL, PAGE_V2)
    changed = wa.web_archive({"url": URL})
    assert changed.success and "Archived" in changed.output
    # force stores even without change
    forced = wa.web_archive({"url": URL, "force": True})
    assert "Archived" in forced.output


def test_archive_read_history(workspace, http):
    http(URL, PAGE_V1)
    wa.web_archive({"url": URL})
    http(URL, PAGE_V2)
    wa.web_archive({"url": URL})
    newest = wa.web_archive_read({"url": URL})
    assert "Version two" in newest.output
    oldest = wa.web_archive_read({"url": URL, "index": 0})
    assert "Version one" in oldest.output
    assert wa.web_archive_read({"url": URL, "index": 9}).success is False


def test_archive_list_and_errors(workspace, http):
    assert "empty" in wa.web_archive_list({}).output.lower()
    http(URL, PAGE_V1)
    wa.web_archive({"url": URL})
    listed = wa.web_archive_list({})
    assert "Spec" in listed.output
    assert wa.web_archive({"url": "not-a-url"}).success is False
    assert wa.web_archive_read({"url": "https://never.example/"}).success is False


def test_archive_text_is_searchable(workspace, http):
    http(URL, PAGE_V1)
    wa.web_archive({"url": URL})
    from tools import doc_retrieval as dr

    res = dr.doc_search({"query": "specification paragraph"})
    assert res.success and "spec" in res.output.lower()
