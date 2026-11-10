# Dynamic Island — UI specification

## Product surface

A compact top-centre KDE Plasma 6 island that expands progressively into a useful control and conversation surface. It is a desktop component, not a browser shell or a full-screen dashboard.

## Visual direction

- Minimal, monochrome-first surfaces with restrained accent colour.
- Strong typographic hierarchy and compact information density.
- Motion communicates state changes; it must not delay input or obscure information.
- Progressive disclosure: compact idle state first, expanded controls and conversation only on demand.
- Avoid gaming HUD styling, decorative graphs and persistent dashboard clutter.

## States

- Compact / idle
- Expanded controls
- Conversation / streaming response
- Listening / transcribing / thinking / speaking
- Approval required
- Notification or activity feedback
- Error / recovery
- Optional gesture mode and optional 3D workspace

## Interaction constraints

- The compact island remains useful when AI is unavailable.
- AI conversation is a panel connected to the existing AgentLoop.
- Microphone capture starts only on explicit push-to-talk activation.
- Camera capture starts only after gesture mode is explicitly enabled.
- The 3D workspace is loaded only when requested; failure must not crash the island.
- Consequential desktop actions require explicit confirmation.

## Implementation ownership

- Overlay and conversation: `dynamic-island/app/ui/`
- State and desktop coordination: `dynamic-island/app/integration/`
- Voice: `dynamic-island/app/voice/`
- Gestures: `dynamic-island/app/gestures/`
- 3D workspace: `dynamic-island/app/workspace3d/`
- KDE integration: `packaging/desktop/`
