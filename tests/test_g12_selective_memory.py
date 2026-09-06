"""G12 — selective memory: stable identity, constellation keyspace +
ownership, BLOB mode.

Hermetic by construction. Proves the keyspace grammar and ownership matrix
(user / agent / system / sibling privacy / legacy keys), that the store
enforces write + read scoping, that BLOB artifacts round-trip without ever
entering text recall, and that the whole path runs through
ToolExecutionService as low-risk auto-approved tools with the audit store
keeping only the params hash (never the remembered value).
"""

from __future__ import annotations

import asyncio
import base64
import re

import pytest  # noqa: F401  (fixtures)

from core.agent.permissions import PermissionEngine
from core.agent.tool_service import ToolExecutionService
from core.decision_logger import DecisionLogger
from providers.types import ToolCall
from tools.registry import ToolRegistry

from memory.keyspace import (
    KIND_AGENT,
    can_read,
    can_write,
    is_valid_agent_id,
    owner_key,
    parse_key,
)
from memory.store import BLOB_MAX_BYTES, MemoryStore
from orbit.memory import get_orbit_memory, reset_orbit_memory
from orbit.tools import build_orbit_tools


# ---------------------------------------------------------------------------
# Keyspace rules
# ---------------------------------------------------------------------------

class TestKeyspace:
    def test_parse_user_system_agent_keys(self):
        assert parse_key("user.notes.favorites") == ("user", "", "notes.favorites")
        assert parse_key("system.orbit.profile") == ("system", "", "orbit.profile")
        assert parse_key("agent.research_1.github.starred") == (
            "agent", "research_1", "github.starred")

    def test_malformed_keys_rejected(self):
        for bad in ("", "user", "user.", "agent..x", "agent.1!.x", "UPPER.x",
                    "freeform.key", "user..x"):
            with pytest.raises(ValueError):
                parse_key(bad)

    def test_owner_strings(self):
        assert owner_key("user") == "user"
        assert owner_key("system") == "system"
        assert owner_key(KIND_AGENT, "research_1") == "agent:research_1"
        with pytest.raises(ValueError):
            owner_key(KIND_AGENT, "no spaces here!")

    def test_agent_id_validation(self):
        assert is_valid_agent_id("main")
        assert is_valid_agent_id("research-1")
        assert is_valid_agent_id("a_1")
        assert not is_valid_agent_id("")
        assert not is_valid_agent_id("has space")
        assert not is_valid_agent_id("x" * 80)

    def test_write_matrix(self):
        user = "user"
        sys = "system"
        ag1 = owner_key(KIND_AGENT, "main")
        ag2 = owner_key(KIND_AGENT, "research-1")
        assert can_write("user.notes.x", user)
        assert not can_write("system.orbit.x", user)
        assert not can_write("agent.main.notes.x", user)
        assert can_write("system.orbit.x", sys)
        assert not can_write("user.notes.x", sys)
        assert can_write("agent.main.notes.x", ag1)
        assert not can_write("agent.research-1.notes.x", ag1)
        assert not can_write("user.notes.x", ag1)
        assert not can_write("system.orbit.x", ag1)

    def test_read_matrix(self):
        user = "user"
        ag1 = owner_key(KIND_AGENT, "main")
        ag2 = owner_key(KIND_AGENT, "research-1")
        assert can_read("agent.research-1.secret.x", user)
        assert can_read("agent.research-1.secret.x", ag1) is False
        assert can_read("agent.research-1.secret.x", ag2)
        assert can_read("user.notes.x", ag1)
        assert can_read("system.orbit.x", ag1)

    def test_legacy_keys_stay_readable_and_user_writable(self):
        assert can_read("some_legacy_key", owner_key(KIND_AGENT, "main"))
        assert can_write("some_legacy_key", "user")
        assert not can_write("some_legacy_key", owner_key(KIND_AGENT, "main"))


# ---------------------------------------------------------------------------
# Store-level ownership + BLOB mode
# ---------------------------------------------------------------------------

class TestStoreOwnership:
    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(data_dir=tmp_path / "mem")

    def test_user_and_agent_write_their_namespace(self, store):
        store.store_owned("user.notes.favorites", "blue", owner="user")
        store.store_owned("agent.main.github.starred",
                          "openai/agents", owner="agent:main")
        assert store.recall("user.notes.favorites") == "blue"
        assert store.recall("agent.main.github.starred") == "openai/agents"

    def test_cross_namespace_write_denied(self, store):
        with pytest.raises(PermissionError):
            store.store_owned("user.notes.favorites", "x", owner="agent:main")
        with pytest.raises(PermissionError):
            store.store_owned("agent.main.x", "x", owner="agent:research-1")
        with pytest.raises(PermissionError):
            store.store_owned("user.notes.favorites", "x", owner="system")

    def test_malformed_key_rejected_on_write(self, store):
        with pytest.raises(ValueError):
            store.store_owned("no_prefix", "x", owner="user")

    def test_legacy_store_still_works(self, store):
        store.store("my_old_style_key", "still here")
        assert store.recall("my_old_style_key") == "still here"

    def test_agent_cannot_read_sibling_or_delete_foreign(self, store):
        store.store_owned("agent.research-1.secret.plan",
                          "do not leak", owner="agent:research-1")
        assert store.recall("agent.research-1.secret.plan",
                            owner="agent:main") is None
        # Admin (None) still sees it.
        assert store.recall("agent.research-1.secret.plan") == "do not leak"
        with pytest.raises(PermissionError):
            store.delete_owned("agent.research-1.secret.plan", owner="agent:main")
        assert store.delete_owned("agent.research-1.secret.plan",
                                  owner="agent:research-1") is True

    def test_search_respects_owner_scope(self, store):
        store.store_owned("agent.main.notes.alpha", "project atlas",
                          owner="agent:main")
        store.store_owned("agent.research-1.notes.beta", "project atlas",
                          owner="agent:research-1")
        store.store_owned("user.notes.gamma", "project atlas", owner="user")
        hits = store.search("atlas", owner="agent:main")
        keys = {h["key"] for h in hits}
        assert "agent.main.notes.alpha" in keys
        assert "user.notes.gamma" in keys
        assert "agent.research-1.notes.beta" not in keys
        # Unscoped sees everything.
        assert len(store.search("atlas")) == 3


class TestBlobMode:
    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(data_dir=tmp_path / "mem")

    def test_blob_round_trip_binary_safe(self, store):
        payload = bytes(range(256)) + b"\x00\xffbinary"
        store.put_blob("agent.main.artifacts.shot1", payload,
                       owner="agent:main", mime="image/png")
        blob = store.get_blob("agent.main.artifacts.shot1", owner="agent:main")
        assert blob is not None
        assert blob["data"] == payload
        assert blob["mime"] == "image/png"
        assert blob["size"] == len(payload)

    def test_blob_ownership_enforced(self, store):
        store.put_blob("agent.research-1.artifacts.report", b"pdf-bytes",
                       owner="agent:research-1", mime="application/pdf")
        # Sibling cannot read the payload or metadata.
        assert store.get_blob("agent.research-1.artifacts.report",
                              owner="agent:main") is None
        assert store.blob_info("agent.research-1.artifacts.report",
                               owner="agent:main") is None
        with pytest.raises(PermissionError):
            store.put_blob("agent.main.artifacts.x", b"nope",
                           owner="agent:research-1")
        # Owner sees metadata only (no payload) via info.
        info = store.blob_info("agent.research-1.artifacts.report",
                               owner="agent:research-1")
        assert info is not None and "data" not in info and info["size"] == 9

    def test_blob_cap_enforced(self, store):
        with pytest.raises(ValueError):
            store.put_blob("user.artifacts.huge", b"x" * (BLOB_MAX_BYTES + 1),
                           owner="user")

    def test_blobs_never_enter_text_recall_or_search(self, store):
        store.store_owned("user.notes.about_shot", "the screenshot summary",
                          owner="user")
        store.put_blob("user.artifacts.shot1", b"raw-image-bytes",
                       owner="user")
        # Text search must not surface the blob payload.
        assert store.search("raw-image-bytes") == []
        assert store.recall("user.artifacts.shot1") is None
        blobs = store.list_blobs(owner="user")
        assert len(blobs) == 1
        assert blobs[0]["key"] == "user.artifacts.shot1"
        assert "data" not in blobs[0]

    def test_blob_upsert_replaces(self, store):
        store.put_blob("user.artifacts.x", b"v1", owner="user")
        store.put_blob("user.artifacts.x", b"v2-longer", owner="user")
        blob = store.get_blob("user.artifacts.x")
        assert blob["data"] == b"v2-longer"


# ---------------------------------------------------------------------------
# Tool path through ToolExecutionService
# ---------------------------------------------------------------------------

def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register_many(build_orbit_tools())
    return reg


def _service(logger) -> ToolExecutionService:
    permissions = PermissionEngine(logger, mode="agent", fail_closed_risky=True)
    return ToolExecutionService(
        registry=_registry(),
        permissions=permissions,
        decision_logger=logger,
        mode="agent",
    )


def _run(service, name, args, trace="g12", session="s12"):
    return asyncio.run(service.execute_tool(
        ToolCall(name=name, arguments=args, id="call-g12"),
        trace_id=trace, session_id=session,
    ))


class TestToolPath:
    @pytest.fixture(autouse=True)
    def seeded_store(self, tmp_path):
        reset_orbit_memory()
        get_orbit_memory(data_dir=tmp_path / "orbit-mem")
        yield
        reset_orbit_memory()

    def test_remember_recall_forget_round_trip(self):
        logger = DecisionLogger()
        service = _service(logger)
        result = _run(service, "orbit.memory_remember", {
            "key": "agent.main.research.ai_browsers",
            "value": "JARVIS Orbit runs Chromium via CDP",
            "owner": "agent", "agent_id": "main",
        })
        assert result.success is True
        result = _run(service, "orbit.memory_recall", {
            "key": "agent.main.research.ai_browsers",
            "owner": "agent", "agent_id": "main",
        })
        assert result.success is True
        assert "CDP" in result.output
        result = _run(service, "orbit.memory_forget", {
            "key": "agent.main.research.ai_browsers",
            "owner": "agent", "agent_id": "main",
        })
        assert result.success is True
        result = _run(service, "orbit.memory_recall", {
            "key": "agent.main.research.ai_browsers",
            "owner": "agent", "agent_id": "main",
        })
        assert result.success is False  # gone

    def test_sibling_agent_recall_denied_gracefully(self):
        service = _service(DecisionLogger())
        r1 = _run(service, "orbit.memory_remember", {
            "key": "agent.research-1.findings.x", "value": "private finding",
            "owner": "agent", "agent_id": "research-1",
        })
        assert r1.success is True
        r2 = _run(service, "orbit.memory_recall", {
            "key": "agent.research-1.findings.x",
            "owner": "agent", "agent_id": "main",
        })
        assert r2.success is False
        assert "readable by" in r2.error

    def test_agent_cannot_write_user_namespace_via_tool(self):
        service = _service(DecisionLogger())
        result = _run(service, "orbit.memory_remember", {
            "key": "user.notes.private", "value": "steal",
            "owner": "agent", "agent_id": "main",
        })
        assert result.success is False
        assert "may not write" in result.error

    def test_artifact_tool_round_trip(self):
        service = _service(DecisionLogger())
        payload = base64.b64encode(b"PNG-BINARY-\x00\x01").decode("ascii")
        r1 = _run(service, "orbit.memory_artifact_save", {
            "key": "agent.main.artifacts.shot1", "data_base64": payload,
            "mime": "image/png", "owner": "agent", "agent_id": "main",
        })
        assert r1.success is True
        r2 = _run(service, "orbit.memory_artifact_get", {
            "key": "agent.main.artifacts.shot1",
            "owner": "agent", "agent_id": "main",
        })
        assert r2.success is True
        assert r2.metadata["mime"] == "image/png"
        assert r2.metadata["data_base64"] == payload

    def test_tools_are_low_risk_and_audited_without_value_leak(self):
        reg = _registry()
        remember = reg.get("orbit.memory_remember")
        assert remember is not None and remember.risk == "low"
        # Forget is not destructive-gated: deletion is bounded to the caller's
        # own namespace by the ownership guard.
        assert reg.get("orbit.memory_forget").is_destructive is False

        logger = DecisionLogger()
        service = _service(logger)
        secret = "super-secret-remembered-value-99"
        result = _run(service, "orbit.memory_remember", {
            "key": "user.notes.token", "value": secret, "owner": "user",
        })
        assert result.success is True
        logger.flush()
        rows = logger.audit.query_trace(trace_id="g12")
        assert rows and rows[0]["tool"] == "orbit.memory"
        assert rows[0]["allowed"] == 1
        blob = "\n".join(str(r) for r in rows).lower()
        assert secret not in blob, "remembered value leaked to audit"
        assert re.fullmatch(r"[0-9a-f]{12}", rows[0]["params_hash"])
