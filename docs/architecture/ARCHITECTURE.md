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


## Dynamic Island core architecture decision — 2026-11-14

### Decision

Keep the production island on **PySide6 QWidget** during the core reliability phase. Do not migrate the production overlay to QML or a Plasma Plasmoid on the basis of benchmark claims that have not been reproduced on the target laptop.

A separate, non-production prototype may compare:

1. The current QWidget overlay.
2. A QWidget host containing QQuickWidget.
3. A dedicated QQuickWindow controlled by a Python QObject backend.

The prototype must use equivalent visuals, states, input behaviour and animation timings. The result must be measured on the target Plasma 6 / Wayland machine before a rendering-stack migration is considered.

### Evidence and corrections

- The island UI is currently implemented in `dynamic-island/app/ui/overlay_window.py` (767 lines at this decision point), not the approximately 2,100 lines quoted in the earlier comparison.
- `IslandController` is a QObject presentation adapter. It exposes an `IslandView` snapshot and Qt signals; it contains no agent execution or permission logic.
- `JarvisBackend` owns the agent worker thread and asyncio loop. It communicates with the Qt application through signals.
- `Workspace3D` already uses a lazily-created QQuickWidget for a separate 3D workspace. That is evidence of existing Qt Quick integration, not evidence that the island itself is QML.
- QML's scene graph can use hardware-accelerated rendering, but GPU acceleration and lower memory use are not guaranteed for every workload or host. No valid target-hardware benchmark currently establishes a performance advantage over the QWidget overlay.
- A Kirigami/Plasmoid compact/full representation is a Plasma applet pattern. It is not a drop-in implementation of a standalone always-on-top overlay.
- QQuickWidget and QQuickWindow are different hosting architectures. QQuickWidget embeds Qt Quick in a QWidget and has an offscreen-rendering path; QQuickWindow is a native Qt Quick window and requires separate lifecycle, focus and platform-window handling. They must not be treated as interchangeable.

### Stable boundaries

- Python remains the application and integration backend.
- `IslandController` remains the presentation-state adapter.
- AgentLoop, JarvisBackend, coordinator, permissions, tools, memory, voice and gestures are not ported to QML.
- The existing KWin script remains responsible for KDE Wayland placement.
- The island must remain usable when AI providers, network access, camera hardware and optional 3D rendering are unavailable.
- No Plasma Plasmoid migration is planned for this phase.

### Core-phase priority

Before changing the rendering stack, fix and verify lifecycle behaviour in the existing implementation. In particular, `IslandWindow.quit_application()` currently calls `AppCoordinator.shutdown()` synchronously from the UI path. The coordinator stops gestures, voice, workspace and backend in sequence; `JarvisBackend.stop()` may join its worker thread for up to ten seconds. This requires a bounded, observable shutdown design and tests so that the UI does not become unresponsive or report completion while a worker is still alive.

### Benchmark acceptance criteria

A prototype comparison is valid only when all candidates use the same state transitions and visual workload. Record:

- Startup-to-first-visible-frame time.
- Idle and animated CPU usage.
- Resident memory after warm-up.
- Frame-time distribution during expand/collapse (not only average FPS).
- Window positioning and resize behaviour under Plasma 6 / Wayland.
- Pointer, keyboard and focus behaviour.
- Clean shutdown time and surviving thread/process count.

Do not use offscreen CI results as a substitute for target GPU/compositor measurements. Until these measurements exist, QWidget remains the production baseline.
