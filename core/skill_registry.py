"""Skill Registry — a discovery-facing index over the skill manifests.

Borrows the MCP-registry pattern (Project JARVIS): manifests are a
catalog you can query, and risk is *host-floored* by the capability
registry a manifest references — a skill cannot under-declare its own
danger. A manifest claiming ``shell.execute`` (CRITICAL) is rated
CRITICAL no matter what it says about itself.

Built on the existing :class:`core.skill_loader.SkillLoader`; no new
dependencies. Search is a lightweight token-overlap scorer over name,
description, capabilities and permissions — enough for real discovery
without dragging an embedding model into the daemon's hot path.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from core.capability_registry import CapabilityRisk, get_capability
from core.skill_loader import get_skill_loader

logger = logging.getLogger("jarvis.skills.registry")

_WORD_RE = re.compile(r"[a-z0-9]+")
_RISK_ORDER = [r.value for r in CapabilityRisk]  # safe, low, medium, high, critical
# Minimum gap between on-disk fingerprint checks so rapid discovery calls don't
# re-stat every manifest file.
_REFRESH_THROTTLE_NS = 2_000_000_000  # 2 seconds


@dataclass
class SkillRecord:
    """One indexed skill manifest with its host-floored risk."""

    name: str
    version: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    supported_modes: list[str] = field(default_factory=list)
    entry_point: str = ""
    max_risk: str = "medium"
    unknown_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


class SkillRegistry:
    """Searchable, risk-floored index of every loaded skill manifest."""

    def __init__(self, loader=None):
        self._loader = loader if loader is not None else get_skill_loader()
        self._records: dict[str, SkillRecord] = {}
        self._index: dict[str, list[str]] = {}
        self._fingerprints: dict[str, tuple[int, int]] = {}
        self._last_check_ns = 0
        self.rebuild()

    # ── build ──────────────────────────────────────────────────────────

    def rebuild(self) -> None:
        self._records = {}
        self._index = {}
        self._fingerprints = self._fingerprint()
        for name, manifest in self._loader.get_all_skills().items():
            record = self._build_record(manifest)
            self._records[name] = record
            for token in self._tokens(record):
                self._index.setdefault(token, []).append(name)
        logger.info("indexed %d skills", len(self._records))

    # ── hot reload ─────────────────────────────────────────────────────

    def _fingerprint(self) -> dict[str, tuple[int, int]]:
        """``{manifest_path: (mtime_ns, size)}`` — cheap change detector."""
        out: dict[str, tuple[int, int]] = {}
        for path in sorted(self._loader.manifests_dir.glob("*.json")):
            try:
                stat = path.stat()
            except OSError:
                continue
            out[str(path)] = (stat.st_mtime_ns, stat.st_size)
        return out

    def _refresh_if_changed(self) -> None:
        """Rebuild lazily when any manifest file changed on disk.

        Throttled so a burst of discovery calls stats the manifests directory
        at most once per window. When a changed fingerprint is seen the
        underlying loader is recreated (reloading the singleton when this
        registry uses it) so edits/additions/deletions all propagate.
        """
        now = time.monotonic_ns()
        if now - self._last_check_ns < _REFRESH_THROTTLE_NS:
            return
        self._last_check_ns = now
        current = self._fingerprint()
        if current == self._fingerprints:
            return
        from core.skill_loader import SkillLoader, get_skill_loader, reload_skills

        if self._loader is get_skill_loader():
            self._loader = reload_skills()
        else:
            self._loader = SkillLoader(self._loader.manifests_dir)
        self.rebuild()

    @staticmethod
    def _build_record(manifest) -> SkillRecord:
        """Build a record, flooring risk to the max referenced capability."""
        risk_idx = 0
        unknown: list[str] = []
        for cap in manifest.capabilities:
            registered = get_capability(cap)
            if registered is None:
                unknown.append(cap)
                continue
            idx = _RISK_ORDER.index(registered.risk.value)
            risk_idx = max(risk_idx, idx)
        return SkillRecord(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            capabilities=list(manifest.capabilities),
            permissions=list(manifest.permissions),
            supported_modes=[str(m) for m in manifest.supported_modes],
            entry_point=manifest.entry_point,
            max_risk=_RISK_ORDER[risk_idx],
            unknown_capabilities=unknown,
        )

    def _tokens(self, record: SkillRecord) -> set[str]:
        text = " ".join(
            [record.name, record.description]
            + record.capabilities
            + record.permissions
        )
        return set(_WORD_RE.findall(text.lower()))

    # ── query ──────────────────────────────────────────────────────────

    def search(self, query: str = "", mode: str | None = None,
               max_risk: str | None = None) -> list[SkillRecord]:
        """Ranked discovery over the catalog.

        Filters by ``mode`` (only skills whose ``supported_modes`` include it)
        and ``max_risk`` (exclusive host-floor ceiling). With no query returns
        the catalog sorted by name; with a query returns token-overlap hits
        ranked best-first.
        """
        self._refresh_if_changed()
        results = list(self._records.values())

        if mode:
            results = [r for r in results if mode in r.supported_modes]
        if max_risk and max_risk in _RISK_ORDER:
            ceiling = _RISK_ORDER.index(max_risk)
            results = [
                r for r in results
                if _RISK_ORDER.index(r.max_risk) <= ceiling
            ]

        query = query.strip().lower()
        if not query:
            return sorted(results, key=lambda r: r.name.lower())

        qtokens = set(_WORD_RE.findall(query))
        if not qtokens:
            return []
        scored = [
            (len(qtokens & self._tokens(r)), r)
            for r in results
        ]
        scored = [(s, r) for s, r in scored if s > 0]
        scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
        return [r for _, r in scored]

    def get(self, name: str) -> SkillRecord | None:
        self._refresh_if_changed()
        return self._records.get(name)

    def count(self) -> int:
        self._refresh_if_changed()
        return len(self._records)

    def summary(self) -> dict[str, Any]:
        self._refresh_if_changed()
        by_risk = Counter(r.max_risk for r in self._records.values())
        return {"total": len(self._records), "by_risk": dict(by_risk)}


_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def reload_skill_registry() -> SkillRegistry:
    global _registry
    _registry = SkillRegistry()
    return _registry
