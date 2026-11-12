# Post-verification backlog addendum — Rust hybrid audit

**Status:** Proposed tasks; not implementation approval.  
**Reference branch:** `dynamic-island-cleanup`  
**Audited baseline:** `7160001bf99472dc6e81ee6729dc906f06750a05`  
**Scope:** Dynamic Island Python/Rust hybrid conversion only. Do not conflate it with the historical Orbit Native browser work.

## 1. Existing research backlog

The expanded external-project and model queue already exists in the master roadmap Revision 3.0:

- `RES-001`–`RES-022`: Sentinel OS security patterns, OSIRIS/geospatial architecture, browser-agent references, workflow orchestration, and KDE/Plasma desktop references.
- `AI-015`–`AI-025`: small-model candidates, including Qwen, FunctionGemma, Granite, Ministral, LFM, SmolLM, Phi and Trim 1.
- `AI-026`–`AI-035`: reproducible tool-calling benchmark, model-quality and cost measurements, routing evaluation, and model provenance.

Keep those IDs and their acceptance criteria unchanged. This addendum introduces only the missing Rust audit workstream; it does not duplicate the existing RES/AI tasks.

## 2. Current Rust status

### 2.1 Dynamic Island hybrid

At the audited cleanup baseline, the active Dynamic Island application is Python/PySide6. Its coordinator and AI bridge use the existing Python AgentLoop and Qt worker/signal architecture. The inspected architecture and application documentation did not identify an integrated Rust service, Unix-socket IPC gateway, PyO3 binding, or Rust runtime dependency.

**Status: NOT STARTED as an integrated runtime conversion.** Rust remains an architectural option, not an implemented dependency.

### 2.2 Historical Orbit Native

The historical `main` branch contains a separate `orbit-native/orbit-core` Rust policy crate. Its documented scope includes URL/network policy, default-deny site permissions, tab lifecycle, private-window PIN handling, session snapshots, error logging and a BrowserController abstraction. The repository README reports 49 headless tests; that count is a repository claim and must be rerun before relying on it.

The WebView2 host was not completed and was removed after binding/API compilation problems. This is not evidence of a working Rust browser, and it is not the Dynamic Island hybrid.

**Decision:** Keep Orbit Native historical and separate. Do not restore its browser prototype into the Dynamic Island branch as part of this work.

## 3. Proposed tasks

| ID | Task | Priority | Dependencies |
|---|---|---:|---|
| RUST-001 | Freeze the boundary between Dynamic Island Rust integration and historical Orbit Native | P1 | None |
| RUST-002 | Re-audit the active branch for Rust sources, build manifests, runtime references and uncommitted local work before implementation | P1 | RUST-001 |
| RUST-003 | Define a versioned local Unix-domain-socket IPC contract between the Python desktop application and an optional Rust service | P1 | RUST-002 |
| RUST-004 | Define IPC security: socket ownership/mode, peer identity, message-size limits, schema validation, request IDs, authorization boundary and safe error handling | P1 | RUST-003 |
| RUST-005 | Benchmark the Python baseline and measure IPC serialization/round-trip overhead under representative workloads | P1 | RUST-002, RUST-003 |
| RUST-006 | Select one narrow Rust responsibility only when profiling or a platform requirement demonstrates a measurable benefit | P1 | RUST-005 |
| RUST-007 | Build a standalone Rust IPC proof of concept with no privileged desktop or agent capabilities | P2 | RUST-003, RUST-004, RUST-006 |
| RUST-008 | Integrate one narrow feature behind the existing Python interface, retaining a Python fallback and a feature switch | P2 | RUST-007 |
| RUST-009 | Test timeouts, cancellation, malformed messages, service crashes, restart recovery, duplicate requests and shutdown | P1 | RUST-008 |
| RUST-010 | Validate clean install, upgrade, uninstall and service lifecycle on the supported KDE/Linux target | P1 | RUST-008, RUST-009 |
| RUST-011 | Compare Unix-socket IPC with PyO3/FFI only if measured latency or deployment constraints justify the comparison | P3 | RUST-005 |
| RUST-012 | Record an explicit ADOPT / DEFER / REJECT decision and update the architecture/implementation roadmap | P1 | RUST-005 through RUST-011 |

## 4. Architecture constraints

- Keep AgentLoop, ModelGateway, memory, PermissionEngine, ToolExecutionService and VerificationEngine in Python unless a measured requirement justifies a specific migration.
- Rust must not become a second agent loop, model router, memory store or permission authority.
- The Python policy layer remains authoritative. A Rust service may perform a bounded operation; it cannot grant itself permission to execute desktop actions.
- IPC must be local-only, versioned, bounded, authenticated to the expected local user/session, and fail closed.
- The service must be optional. The Dynamic Island must still launch and provide basic desktop functionality if the Rust service is absent or crashes.
- Do not migrate UI rendering to Rust as part of this workstream.
- Do not add a Rust dependency to the installer until the proof of concept and packaging tests justify it.

## 5. Execution gate and order

1. Finish the PKG-001 retest after the isolated autostart/KWin packaging corrections. Preserve the previous smoke report; append the new run rather than replacing historical evidence.
2. Complete the real-display Wayland test. The prior no-output session is still a blocker for visual placement and interaction claims.
3. Reconcile the runtime guide, launch report, decision record and packaging report. Keep any unresolved item PARTIAL or BLOCKED.
4. Only then begin implementation-oriented RES/AI/RUST tasks. Read-only research and benchmark specification may be prepared earlier.
5. Run the Python baseline before selecting a Rust component. If no meaningful bottleneck or platform requirement is demonstrated, defer the hybrid conversion.

### Acceptance criteria for the Rust workstream

The workstream is complete only when there is a reviewed IPC contract, a reproducible Python-vs-Rust benchmark, a narrow component justified by evidence, an optional integration with Python fallback, passing fault/security/lifecycle tests, and verified packaging. Otherwise record **DEFER** with the evidence; do not create a Rust service merely to claim that a hybrid conversion has started.

## 6. Source references

- [Dynamic Island architecture](https://github.com/Railgunonyx1/JARVIS/blob/dynamic-island-cleanup/docs/architecture/ARCHITECTURE.md)
- [Dynamic Island application README](https://github.com/Railgunonyx1/JARVIS/blob/dynamic-island-cleanup/dynamic-island/README.md)
- [Historical Orbit Native README](https://github.com/Railgunonyx1/JARVIS/blob/main/orbit-native/README.md)
- [Historical Orbit Native migration report](https://github.com/Railgunonyx1/JARVIS/blob/main/docs/ORBIT-NATIVE-MIGRATION.md)
- [Orbit host-removal commit](https://github.com/Railgunonyx1/JARVIS/commit/939c3b3adc7ce6d4c1f282c1042551410fd4241c)
