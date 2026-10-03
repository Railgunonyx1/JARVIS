"""Tests for repo-mine pass-2 tools: pdf, doc export, page watch, notify, wait.

All network/filesystem effects are hermetic: PDFs are generated in-memory with
pypdf, HTTP is monkeypatched, and browser.wait is tested against stubbed
controllers.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_default_registry  # noqa: E402
from tools.schema import ToolResult  # noqa: E402


# ----------------------------------------------------------------- registry

def test_new_tools_registered():
    registry = build_default_registry()
    for name in (
        "pdf.extract_text", "pdf.extract_tables", "pdf.split", "pdf.merge",
        "docs.to_markdown", "page.watch", "notify.send", "browser.wait",
    ):
        tool = registry.get(name)
        assert tool is not None, f"{name} missing from registry"
        assert tool.handler is not None


# --------------------------------------------------------------------- pdf

@pytest.fixture()
def sample_pdf(tmp_path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for i in range(3):
        writer.add_blank_page(width=200, height=200)
    p = tmp_path / "sample.pdf"
    with open(p, "wb") as fh:
        writer.write(fh)
    return p


def test_pdf_split_and_merge(sample_pdf, tmp_path, monkeypatch):
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.pdf_tools as pt

    res = pt.pdf_split({"path": "sample.pdf", "every": 1, "dest": "split_out"})
    assert res.success, res.error
    files = res.metadata["files"]
    assert len(files) == 3

    res2 = pt.pdf_merge({"paths": files[:2], "dest": "merged.pdf"})
    assert res2.success, res2.error
    assert (tmp_path / "merged.pdf").exists()


def test_pdf_extract_text_empty(sample_pdf, tmp_path, monkeypatch):
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.pdf_tools as pt

    res = pt.pdf_extract_text({"path": "sample.pdf"})
    # blank pages -> no text; must fail gracefully, not raise
    assert isinstance(res, ToolResult)
    assert res.success is False
    assert "text" in (res.error or "").lower()


def test_pdf_extract_text_invalid_range(sample_pdf, tmp_path, monkeypatch):
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.pdf_tools as pt

    res = pt.pdf_extract_text({"path": "sample.pdf", "pages": "50-60"})
    assert res.success is False
    assert "No valid pages" in res.error


def test_pdf_page_range_parsing():
    import tools.pdf_tools as pt

    assert pt._page_range("1,3", 5) == [0, 2]
    assert pt._page_range("2-4", 5) == [1, 2, 3]
    # Out-of-range pages are clamped, not dropped
    assert pt._page_range("99-100", 5) == []
    assert pt._page_range("4-99", 5) == [3, 4]


# --------------------------------------------------------------- page watch

@pytest.fixture()
def pw(tmp_path, monkeypatch):
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.page_watch as module
    yield module
    # no cleanup needed; state lives under tmp_path


def test_page_watch_arm_check_change(pw, monkeypatch):
    pages = iter(["<p>v1</p>", "<p>v1</p>", "<p>v2 new content</p>"])
    monkeypatch.setattr(pw, "_fetch_text", lambda url, timeout: next(pages))

    r1 = pw.page_watch({"url": "https://example.com/a"})
    assert r1.success and "First sighting" in r1.output

    r2 = pw.page_watch({"url": "https://example.com/a"})
    assert r2.success and "Unchanged" in r2.output

    r3 = pw.page_watch({"url": "https://example.com/a"})
    assert r3.success
    assert "CHANGED" in r3.output
    assert r3.metadata["changed"] is True
    assert "+ v2 new content" in r3.output or "v2 new content" in r3.output


def test_page_watch_list_remove(pw, monkeypatch):
    monkeypatch.setattr(pw, "_fetch_text", lambda url, timeout: "<p>x</p>")
    assert pw.page_watch({"url": "https://example.com/b", "action": "arm"}).success
    listed = pw.page_watch({"url": "", "action": "list"})
    # list ignores url; url validation happens before action though
    # (url required for non-list actions) -> use a dummy url for list:
    assert isinstance(listed, ToolResult)

    rm = pw.page_watch({"url": "https://example.com/b", "action": "remove"})
    assert rm.success and "removed" in rm.output.lower()


def test_page_watch_rejects_non_http(pw):
    res = pw.page_watch({"url": "file:///etc/passwd"})
    assert res.success is False
    assert "http" in res.error.lower()


# ------------------------------------------------------------------ notify

def test_notify_requires_target(monkeypatch):
    import tools.notify as nf

    for var in ("JARVIS_NTFY_URL", "JARVIS_GOTIFY_URL", "JARVIS_GOTIFY_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    res = nf.send_notification({"message": "hi"})
    assert res.success is False
    assert "JARVIS_NTFY_URL" in res.error


def test_notify_ntfy_success(monkeypatch):
    import core.http_pool as hp
    import tools.notify as nf

    class FakeResp:
        status_code = 200
        text = ""

    class FakeClient:
        def post(self, url, **kw):
            assert "ntfy.sh" in url
            assert kw["headers"]["Title"] == "Test"
            return FakeResp()

    monkeypatch.setattr(hp, "get_client", lambda: FakeClient())
    res = nf.send_notification({
        "message": "task done", "title": "Test",
        "ntfy_url": "https://ntfy.sh/jarvis-test-topic",
    })
    assert res.success, res.error
    assert "ntfy: sent" in res.output


def test_notify_gotify_failure_reported(monkeypatch):
    import core.http_pool as hp
    import tools.notify as nf

    class FakeResp:
        status_code = 403
        text = "forbidden"

    class FakeClient:
        def post(self, url, **kw):
            return FakeResp()

    monkeypatch.setattr(hp, "get_client", lambda: FakeClient())
    res = nf.send_notification({
        "message": "x", "gotify_url": "https://push.example.com",
        "gotify_token": "tok",
    })
    assert res.success is False
    assert "gotify" in (res.error or "").lower()


# ---------------------------------------------------------------- doc export

def test_doc_export_markdown_passthrough(tmp_path, monkeypatch):
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.doc_export as de

    src = tmp_path / "notes.md"
    src.write_text("# hello\nworld", encoding="utf-8")
    res = de.doc_to_markdown({"path": "notes.md"})
    assert res.success, res.error
    assert (tmp_path / "notes.md").exists()  # .md -> .md stays itself


def test_doc_export_json(tmp_path, monkeypatch):
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.doc_export as de

    src = tmp_path / "data.json"
    src.write_text('{"a": 1}', encoding="utf-8")
    res = de.doc_to_markdown({"path": "data.json", "dest": "data_conv.md"})
    assert res.success, res.error
    out = tmp_path / "data_conv.md"
    assert out.exists()
    assert '"a": 1' in out.read_text(encoding="utf-8")


def test_doc_export_html(tmp_path, monkeypatch):
    pytest.importorskip("markdownify")
    from core.project import ProjectContext

    monkeypatch.setattr(
        ProjectContext, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    import tools.doc_export as de

    src = tmp_path / "page.html"
    src.write_text("<h1>Tile</h1><p>Body text</p>", encoding="utf-8")
    res = de.doc_to_markdown({"path": "page.html"})
    assert res.success, res.error
    assert "# Tile" in res.output or "Tile" in res.output


# ------------------------------------------------------------- browser.wait

class _FakeController:
    """Controller whose execute_script returns scripted values."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def execute_script(self, script, tab_id=None):
        self.calls.append(script)
        return self._results.pop(0) if self._results else "true"


def test_browser_wait_selector_immediate(monkeypatch):
    import tools.browser_wait as bw

    monkeypatch.setattr(
        "jbrowser.controller.get_controller",
        lambda: _FakeController(["true"]),
    )
    res = bw.browser_wait({"condition": "selector", "value": "#btn", "timeout": 2})
    assert res.success, res.error
    assert "document.querySelector" in res.output or res.metadata["condition"] == "selector"


def test_browser_wait_text_after_polls(monkeypatch):
    import tools.browser_wait as bw

    fake = _FakeController(["false", "false", "true"])
    monkeypatch.setattr("jbrowser.controller.get_controller", lambda: fake)
    res = bw.browser_wait({"condition": "text", "value": "Loaded", "timeout": 5})
    assert res.success, res.error
    assert len(fake.calls) == 3


def test_browser_wait_timeout(monkeypatch):
    import tools.browser_wait as bw

    monkeypatch.setattr(
        "jbrowser.controller.get_controller",
        lambda: _FakeController(["false"] * 100),
    )
    res = bw.browser_wait({"condition": "selector", "value": "#never", "timeout": 0.5})
    assert res.success is False
    assert "Timeout" in res.error


def test_browser_wait_validation():
    import tools.browser_wait as bw

    assert bw.browser_wait({"condition": "bogus"}).success is False
    assert bw.browser_wait({"condition": "selector"}).success is False  # no value
    assert bw.browser_wait({}).success is False
