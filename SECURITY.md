# Security Policy — JARVIS Dynamic Island

JARVIS Dynamic Island integrates a desktop UI with an AI agent capable of invoking local tools. Security controls are part of the runtime boundary, not optional UI behaviour.

## Security invariants

1. **Single tool execution boundary:** agent tool calls pass through `ToolExecutionService`; adapters must not call tool executors directly.
2. **Fail-closed permissions:** mutating or consequential operations require the configured permission decision. If approval cannot be obtained, deny the operation.
3. **Secret redaction:** credentials and sensitive values must be redacted before tool output enters model context or logs.
4. **Post-execution verification:** changes must be checked against the resulting filesystem or environment state before being reported as complete.
5. **Explicit device activation:** microphone capture is push-to-talk only. Camera capture starts only after gesture mode is explicitly enabled. No background wake-word listener is supported.
6. **Desktop action confirmation:** actions with external or destructive effects must retain their confirmation boundary.

## Reporting a vulnerability

Do not publish exploitable details in a public issue. Use GitHub's private vulnerability reporting for this repository where available, or contact the repository maintainer privately with the affected component, impact, and a minimal reproduction. Do not include live credentials or personal data in a report.

## Supported scope

The supported desktop target is KDE Plasma 6 on Linux. Security checks that depend on a live compositor, physical devices, or configured model providers must be validated on the target system; headless CI is not proof of those behaviours.
