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
