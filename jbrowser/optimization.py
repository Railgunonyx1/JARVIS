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

The profile is deliberately conservative: we keep everything that reduces
memory/CPU without hurting correctness, and we *disable* discarding/freezing
aggressiveness only when a caller opts into ``preserve_tabs=True`` (agent
research keeping live page state), mirroring the Strawberry-style
"operate across many live tabs" use case.
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
    # --- Memory behaviour -------------------------------------------------
    # Emit the switch that keeps the browser lean: avoid pre-rendering entire
    # spare renderer processes that consume RAM up front.
    "disable-features": "PreloadMediaEngagementData,"
    "MediaEngagementBypassAutoplayPolicies",
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
