# Dynamic Island architecture

## Runtime layers

1. **Desktop shell:** PySide6 overlay and conversation panel under `dynamic-island/app/ui/`.
2. **Coordinator:** owns lifecycle and routes UI, voice, gesture and desktop-action events.
3. **AI bridge:** `JarvisBackend` runs the existing agent runtime on a worker thread and communicates with Qt through signals.
4. **Agent runtime:** AgentLoop, provider router, harness, tool registry, permissions, ToolExecutionService and verification.
5. **State services:** memory, event bus, telemetry and observability.
6. **Platform integration:** KDE desktop entry, autostart and KWin Wayland placement helper.

## Optional subsystems

- Voice uses explicit push-to-talk. STT and TTS engines are loaded as needed.
- Gesture recognition is opt-in; the camera is not opened during normal startup.
- The 3D workspace is constructed and loaded only after a user request.

## Dependency direction

The UI depends on the integration layer. The integration layer may call the shared AI runtime. The core runtime must not depend on Qt widgets or Dynamic Island UI classes. Desktop actions must flow through the established permission and verification boundary.

## Startup contract

The island must start without API keys, local model services, camera hardware or a 3D-capable GPU. Missing optional capabilities should produce a recoverable status, not prevent the compact island from appearing.

## Island presentation decision — 2026-11-14

**Decision: retain the existing PySide6 QWidget implementation for the Dynamic Island core. Do not migrate the production pill to QML yet.**

The current implementation already has a QWidget overlay, a 240 ms geometry animation, compact/expanded states, pointer hover/click handling, status signals, lazy conversation-panel construction, and explicit coordinator shutdown. Qt Quick is currently isolated to the optional 3D workspace and is loaded lazily.

A QML rewrite has not demonstrated a measurable benefit on the target hardware. QML does not guarantee GPU acceleration or smoother animation, and the existing Python `IslandController.view` is a Python property returning a dataclass—not a declared Qt `Property` with a notify signal. A QML bridge therefore requires an explicit, tested QObject API; the proposed context-property binding is not a drop-in change.

### Alternatives retained for a controlled prototype

1. **A — QWidget baseline:** current implementation, unchanged.
2. **B — QWidget + QQuickWidget:** QML content embedded in the current QWidget host. Evaluate the additional offscreen composition and render-loop costs.
3. **C — dedicated QQuickWindow:** Qt Quick scene graph in its own window, with a narrow QObject bridge to the Python controller. Evaluate window flags, Wayland placement, focus and KWin integration separately.

Do not select B or C based on assumed GPU acceleration. Compare equivalent visuals and interactions on the actual target machine. Record idle CPU, resident memory, startup-to-visible time, animation frame-time consistency, input latency, focus behaviour, and placement reliability. Include the active Qt rendering backend and GPU driver in the results. Keep the QWidget implementation as the fallback.

### Bridge contract if a prototype is justified

- Python remains authoritative for application lifecycle, coordinator state, permissions, approvals and desktop actions.
- The presentation bridge exposes only typed, read-only status/detail properties and explicit user-intent signals.
- Every QML-facing property has a Qt notify signal; do not expose a mutable dataclass as an implicit QML API.
- QML owns presentation and animation only. It must not call agent tools, access providers, or bypass the approval boundary.
- The overlay window and KWin placement integration remain separate from the visual component.
- Do not introduce a Plasma Plasmoid or LayerShellQt migration as part of this experiment.

### Core verification boundary

The current code inspection confirms that expansion sets focus on the conversation input, but that alone does not prove the top-level overlay receives keyboard focus correctly under KDE Wayland. Verify activation, typing, Tab traversal, Escape/collapse behaviour, pointer interaction, and focus restoration on a live Plasma session. Do not claim this is covered by offscreen CI.

The approved core phase remains limited to startup/shutdown, top-centre placement, expand/collapse animation, and keyboard/pointer focus. Notifications, multi-monitor feature work, launcher, AI panel expansion, voice changes and dock remain deferred.
