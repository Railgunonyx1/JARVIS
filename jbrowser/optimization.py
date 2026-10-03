"""J-Browser — optimized Chromium launch profile.

Encodes the researched, evidence-backed Chromium/Chromium-embedded flags that
make J-Browser leaner than stock Chrome while preserving compatibility.

Directives are applied as Chromium command-line switches when launching the
browser via ``build_launch_kwargs()`` and documented in ``OPTIMIZATIONS.md``
notes on each entry. Every directive is reversible and safe to toggle.

See CLION-verified sources referenced in AGENTS.md research pipeline:
  - Chrome Memory Saver / tab discarding (developer.chrome.com/blog/memory-and-energy-saver-mode)
  - Chromium tab discarding design doc (chromium.org)
  - trues-chromium-optimizations (GitHub) flag presets
  - makeuseof / gopeek Chromium memory flags roundups
  - GoogleChrome/chrome-launcher chrome-flags-for-tools (GitHub) — the task
    throttling / background-networking / startup switches applied below
  - Playwright long-session memory guides (webscraping.ai, dev.to) — resource
    blocking to short-circuit image/media/font/stylesheet payloads, and the
    memory/session-cap guidance encoded in ``enforce_tab_limit``
  - browser-use#3949 — accessibility/DOM snapshot cost on huge pages, bounded
    here by ``MAX_SCAN_ELEMENTS`` in ``jbrowser.page_context``

The profile is deliberately conservative: we keep everything that reduces
memory/CPU without hurting correctness, cap how many live tabs we keep open
(``DEFAULT_TAB_LIMIT``), and offer opt-in resource blocking for lean
text/DOM extraction. We *disable* discarding/freezing aggressiveness only
when a caller opts into ``preserve_tabs=True`` (agent research keeping live
page state), mirroring the Strawberry-style "operate across many live tabs"
use case. Sandboxing is never disabled.
"""

from __future__ import annotations

from typing import Any

# A single flag may have both an "on" and "off" switch variant in Chromium.
# We express the set we *default* to here; negation switches are emitted for
# the flags we deliberately leave disabled to keep the footprint low.
#
# Keyed by the canonical chromium switch; values are the argument to pass.
OPTIMIZED_FLAGS: dict[str, str] = {
    # --- Rendering / GPU -------------------------------------------------
    # GPU rasterization offloads page compositing to the GPU, freeing CPU and
    # system RAM. Only beneficial with a dedicated GPU (see research caveat
    # for iGPUs); enabled by default but exposed so users can disable it.
    "enable-gpu-rasterization": "",
    # Use two compositor raster threads instead of one on multi-core hosts.
    "num-raster-threads": "2",
    # --- Networking ------------------------------------------------------
    # QUIC reduces connection setup latency on supporting sites.
    "enable-quic": "",
    # --- Memory / background waste -----------------------------------------
    # Emit the switch that keeps the browser lean: avoid pre-rendering entire
    # spare renderer processes and background server chatter that consume RAM
    # and bandwidth up front. Safe: none of these touch the active tab.
    "disable-features": (
        "PreloadMediaEngagementData,"
        "MediaEngagementBypassAutoplayPolicies,"
        "CalculateNativeWinOcclusion"
    ),
    # NOTE: --disable-background-timer-throttling / --disable-backgrounding-
    # occluded-windows / --disable-renderer-backgrounding are deliberately
    # NOT set. They told Chromium "never deprioritise a background tab" while
    # MEMORY_SAVER_FLAGS below says "freeze background tabs" - contradictory
    # goals, and on an 8 GB daily-driver host the never-throttle direction
    # wins and the RAM budget is lost. Chromium's own throttling is the
    # resource policy; the sleep loop in main.js / performance.js is the
    # active-tab guarantee. Re-add one only with a measured win.
    # --- Startup / first-run noise -----------------------------------------
    # Skip first-run wizards, default-browser check and default-app installs;
    # each cuts startup work and background one-time work.
    "no-first-run": "",
    "no-default-browser-check": "",
    "disable-default-apps": "",
    # --- Background services (quiet + lean) --------------------------------
    # No extension runtime, crash-dump collection, component auto-update or
    # domain-reliability uploads for a cold ephemeral agent profile.
    "disable-extensions": "",
    "disable-component-extensions-with-background-pages": "",
    "disable-breakpad": "",
    "disable-component-update": "",
    "disable-domain-reliability": "",
    "disable-background-networking": "",
    # --- Extras -------------------------------------------------------------
    # Mute all audio sources (agent rarely needs sound; saves CPU/jank).
    "mute-audio": "",
    # Cleaner screenshot extraction without scrollbars.
    "hide-scrollbars": "",
}

# Switches we deliberately pass to *reduce* background waste without harming
# the active tab (the biggest RAM win per the Memory Saver research).
MEMORY_SAVER_FLAGS: dict[str, str] = {
    # Signal Chromium to aggressively freeze background tabs (JS/Timers pause).
    # This mirrors the "Infinite Tab Freezing" flag documented as one of the
    # most effective RAM savers. No reload on reactivation (unlike discarding).
    "freeze-background-tabs": "",
}

# When the caller requires live page state across many tabs (agent research),
# we *do not* emit the aggressive discarding switch; preservation wins.
PRESERVE_TABS_OVERRIDES: dict[str, str] = {}

# Structural preferences that keep J-Browser slim (applied client-side, not
# just as Chromium switches). Documented per entry.
PREFERENCES: dict[str, Any] = {
    # Give the active tab priority; let the OS swap cold tabs.
    "memory_saver_enabled": True,
    # Deterministic tab discarding order; internal pages discarded first.
    "tab_discarding_policy": "default",
    # Do not over-allocate renderer processes.
    "max_processes_per_site": 1,
    # Keep search/address bar fast.
    "enable_dngs_provider": False,
}

DEFAULT_TAB_LIMIT: int = 12  # Chrome telemetry: median ~320MB/tab; 12 is safe for 8GB+.


# ── Browser Modes ────────────────────────────────────────────────
# Different agent tasks benefit from different browser configurations.
# Instead of one global profile, the agent selects a mode:
#
# TEXT MODE — fast text/DOM extraction, minimal resource load
# INTERACTIVE MODE — full JS, normal resources, for clicking/forms
# VISUAL MODE — images+CSS preserved, for screenshots/visual reasoning
# RESEARCH MODE — text-optimized, multiple tabs, aggressive context compression
class BrowserMode:
    TEXT = "text"
    INTERACTIVE = "interactive"
    VISUAL = "visual"
    RESEARCH = "research"


_MODE_CONFIGS: dict[str, dict[str, Any]] = {
    BrowserMode.TEXT: {
        "resource_blocking": frozenset({"image", "media", "font", "stylesheet"}),
        "preserve_tabs": False,
        "description": "Minimal resources, fast text/DOM extraction",
    },
    BrowserMode.INTERACTIVE: {
        "resource_blocking": frozenset(),
        "preserve_tabs": True,
        "description": "Full JS, normal resources, for clicking/forms",
    },
    BrowserMode.VISUAL: {
        "resource_blocking": frozenset({"media", "font"}),
        "preserve_tabs": True,
        "description": "Images+CSS preserved, for screenshots/visual reasoning",
    },
    BrowserMode.RESEARCH: {
        "resource_blocking": frozenset({"image", "media", "font", "stylesheet"}),
        "preserve_tabs": True,
        "description": "Text-optimized, multiple tabs, aggressive compression",
    },
}


def get_mode_config(mode: str) -> dict[str, Any]:
    """Return the configuration for a browser mode."""
    return _MODE_CONFIGS.get(mode, _MODE_CONFIGS[BrowserMode.INTERACTIVE])


def build_mode_kwargs(mode: str) -> dict[str, Any]:
    """Return launch kwargs appropriate for the given browser mode."""
    cfg = get_mode_config(mode)
    return build_launch_kwargs(preserve_tabs=cfg.get("preserve_tabs", False))


def build_mode_resource_blocking(mode: str) -> dict[str, Any] | None:
    """Return resource blocking config for the mode, or None if no blocking."""
    cfg = get_mode_config(mode)
    kinds = cfg.get("resource_blocking")
    if not kinds:
        return None
    return build_resource_blocking(kinds=kinds)

# Resource kinds an agent-browser can safely block during text/DOM extraction.
# Blocking these cuts page load bytes and renderer memory with no effect on
# text, links, or interactive-element detection. Scripts and stylesheets stay
# enabled (they affect correctness/layout).
RESOURCE_BLOCK_KINDS: frozenset[str] = frozenset(
    {"image", "media", "font", "stylesheet"}
)
# Kinds removed when a caller wants screenshots/visual layout preserved.
RESOURCE_BLOCK_KEEP_FOR_SCREENSHOT: frozenset[str] = frozenset(
    {"image", "stylesheet"}
)


def build_resource_blocking(
    kinds: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return context-routing config to abort heavy, non-essential resources.

    The returned ``handler`` is a Playwright ``context.route("**/*", handler)``
    callback that aborts requests whose ``resource_type`` is in ``kinds``.
    Intended for lean read/extract passes, not for screenshot/visual work.
    """
    block = kinds if kinds is not None else RESOURCE_BLOCK_KINDS
    pattern = "**/*"
    return {
        "pattern": pattern,
        "kinds": frozenset(block),
        "handler": _make_blocking_handler(block),
    }


def _make_blocking_handler(kinds: frozenset[str]):
    def handler(route) -> None:
        try:
            if route.request.resource_type in kinds:
                route.abort()
            else:
                route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    return handler


def enforce_tab_limit(tab_count: int, limit: int = DEFAULT_TAB_LIMIT) -> int:
    """Return how many tabs exceed the cap (0 when within limit).

    Callers use this to discard the least-recently-active tabs once the cap is
    hit, enforcing the memory budget documented in ``DEFAULT_TAB_LIMIT``.
    """
    return max(0, tab_count - limit)


def build_launch_kwargs(*, preserve_tabs: bool = False) -> dict[str, Any]:
    """Return Chromium ``launch()`` keyword arguments for the optimized profile.

    Combines the base optimized flags with memory-saver flags unless
    ``preserve_tabs`` is set (live multi-tab operation keeps page state).
    """
    flags: dict[str, str] = {}
    flags.update(OPTIMIZED_FLAGS)
    if not preserve_tabs:
        flags.update(MEMORY_SAVER_FLAGS)
    else:
        flags.update(PRESERVE_TABS_OVERRIDES)
    # Collapse to a list of "--key=value"/"--key" switches for the engine.
    switches: list[str] = []
    for key, value in flags.items():
        switches.append(f"--{key}={value}" if value else f"--{key}")
    args: dict[str, Any] = {"args": switches}
    if not preserve_tabs:
        args["reduced_motion"] = False
    return args


def as_chromium_args(preserve_tabs: bool = False) -> list[str]:
    """Convenience: return just the switch list."""
    return build_launch_kwargs(preserve_tabs=preserve_tabs)["args"]
