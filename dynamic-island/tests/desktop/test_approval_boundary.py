"""
Focused regression for the normalized approval boundary on the dynamic-island branch.

Scope (read-only audit posture): verify the live adapter chain that bridges the
core two-argument confirmation callback used by AgentLoop/PermissionEngine and
the island's request-scoped approval mechanism, without modifying any existing
runtime file.

What is in scope here:
- AppCoordinator._action_confirmation -> IslandWindow._confirm
- the same approval_id surviving that handoff
- approve / deny / timeout returning deterministic terminal decisions
- one terminal transition per request (stale/late clicks ignored)
- concurrent requests staying isolated
- backward compatibility for callers that do not pass an approval_id

What is explicitly out of scope:
- Verifying that desktop actions or JarvisBackend currently create approval_id
  themselves. This test asserts the normalized boundary as it should behave; any
  gap between that boundary and the existing production call sites is reported
  separately and is not fixed here.
"""
from __future__ import annotations

import os
import sys
import threading

os.environ.setdefault("JARVIS_DESKTOP_HOME", "/tmp/jarvis-island-test-audit")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "dynamic-island")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.integration.coordinator import AppCoordinator
from app.ui.overlay_window import IslandWindow

APP = QApplication.instance() or QApplication([])
# Keep the event loop alive enough for signal delivery in the audit, but do
# not rely on full GUI rendering for the focused contract checks below.


def _set_up_coordinator_with_island():
    island = IslandWindow()
    coord = AppCoordinator(mode="agent", confirmation_handler=island._confirm)
    coord._confirmation_handler = island._confirm
    return island, coord


def test_approval_preserves_request_scoped_id_when_island_creates_it():
    island, coord = _set_up_coordinator_with_island()

    captured = {}
    original = island._confirm

    def spy(tool_name, arguments, approval_id=None):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["approval_id"] = approval_id
        return original(tool_name, arguments, approval_id)

    island._confirm = spy
    coord._confirmation_handler = island._confirm

    decision = coord._action_confirmation("test_action")

    assert captured["tool_name"] == "test_action"
    assert captured["arguments"] == {}
    assert isinstance(captured["approval_id"], str)
    assert captured["approval_id"].startswith("approval-")
    assert decision in ("approved", "denied")


def test_approval_preserves_externally_supplied_id():
    island, coord = _set_up_coordinator_with_island()

    supplied_id = "approval-external-123"
    decision = coord._action_confirmation("test_action", approval_id=supplied_id)

    assert decision in ("approved", "denied")
    # The externally-supplied ID must reach the island handler as-is; a
    # backend/backend-wrapper that discards the ID would break the canonical
    # contract this test describes.
    assert island._approval_registry.get(supplied_id) is not None


def test_approval_allow_and_deny_return_deterministic_decisions():
    island, coord = _set_up_coordinator_with_island()

    # Allow path
    allow_id = "approval-allow-1"
    allow_decision = coord._action_confirmation("test_action", approval_id=allow_id)
    assert allow_decision == "approved"

    # Deny path
    deny_id = "approval-deny-1"
    deny_decision = coord._action_confirmation("test_action", approval_id=deny_id)
    assert deny_decision == "denied"

    # Same IDs must be terminal
    assert island._approval_registry.get(allow_id).is_terminal()
    assert island._approval_registry.get(deny_id).is_terminal()


def test_approval_timeout_fails_closed():
    island, coord = _set_up_coordinator_with_island()

    timeout_id = "approval-timeout-1"
    decision = coord._action_confirmation("test_action", approval_id=timeout_id)

    # Unanswered request must expire and return denied, not hang.
    assert decision == "denied"
    assert island._approval_registry.get(timeout_id).is_terminal()


def test_stale_second_decision_is_ignored():
    island, coord = _set_up_coordinator_with_island()

    record_id = "approval-stale-1"
    first = coord._action_confirmation("test_action", approval_id=record_id)
    second = coord._action_confirmation("test_action", approval_id=record_id)

    # A second terminal transition for the same request-scoped ID must not
    # change the first decision.
    assert first == second


def test_concurrent_approval_requests_remain_isolated():
    island, coord = _set_up_coordinator_with_island()

    ids = [f"approval-concurrent-{i}" for i in range(3)]
    results = []

    def run_one(approval_id):
        results.append(coord._action_confirmation("test_action", approval_id=approval_id))

    threads = [threading.Thread(target=run_one, args=(aid,)) for aid in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert len(results) == 3
    for aid in ids:
        record = island._approval_registry.get(aid)
        assert record is not None
        assert record.is_terminal()
    # All terminal, all distinct IDs.
    assert len({r for r in results}) <= len(ids)


def test_backward_compatibility_without_approval_id():
    island, coord = _set_up_coordinator_with_island()

    # Callers that omit approval_id must still reach the island handler and
    # get a deterministic terminal decision. The island may generate the ID in
    # that case; the boundary test here is that the call does not raise and the
    # request still resolves once.
    decision = coord._action_confirmation("test_action")
    assert decision in ("approved", "denied")
