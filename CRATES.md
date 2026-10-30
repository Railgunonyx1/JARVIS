# Crates

Current workspace layout:

- `crates/jarvis-core` — application state, events, lifecycle, and the core runtime.
- `crates/jarvis-ui` — UI abstraction and placeholder GTK4 runner.
- `apps/jarvis-island` — main binary for the Dynamic Island.

Current intended direction:

- Hybrid by default at the foundation stage: Rust core + event system first, with a
  GTK4 + Relm4 overlay added as the UI backend once GTK dependencies are available.
- The UI crate is feature-gated behind `jarvis-ui/gtk4` so the workspace can still be
  inspected before GTK is installed.

What is intentionally minimal right now:

- No audio, gesture, or AI crates yet.
- No layer-shell implementation yet; that is the next real UI milestone.
- The GTK runner currently logs requests and returns errors rather than opening a
  window.

Next visible milestone:

- Wire GTK4 + Relm4 + gtk4-layer-shell in `crates/jarvis-ui` so the overlay can run
  on KDE Wayland.
