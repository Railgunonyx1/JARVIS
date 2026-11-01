# JARVIS Dynamic Island — Phase 0 Decisions

Status: Phase 0 draft, for council review
Branch: `dynamic-island`
Baseline commit: `b1f5051`
Companion documents:
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/COMPONENT-BOUNDARIES.md`
- `docs/architecture/IMPLEMENTATION-ROADMAP.md`
Guidance source: `tmp/dynamic-island-council/FULL-REPOSITORY-COUCIL-AUDIT.md`

## 1. Decisions frozen for Phase 0

### 1.1 Product direction

| # | Decision | Notes |
| --- | --- | --- |
| D-01 | The Dynamic Island product direction is Qt Quick / QML frontend with a Python backend. | This is the council-preferred posture, not a fully implemented one. |
| D-02 | GTK4 is superseded for the planned product direction unless the team deliberately decides otherwise. | The current Rust/GTK prototype is not the product foundation. |
| D-03 | The desktop target is KDE Wayland on Bazzite first. | Mode-switching and fallback strategy are unresolved. |
| D-04 | Activation is explicit user interaction, not a background wake word. | Keeps Phase 0 scope small. |
| D-05 | The first UI is a minimal Dynamic Island, not a general-purpose dashboard. | Collapsed pill, expanded pill, one status indicator, one message area, one interaction button. |

### 1.2 Runtime architecture

| # | Decision | Notes |
| --- | --- | --- |
| D-06 | The application is split into a Python backend process and a Qt Quick / QML frontend process. | Exact IPC mechanism is unresolved. |
| D-07 | The backend owns application truth. | Frontend is presentation, not a second kernel. |
| D-08 | Rust is optional and narrow. | Only for justified performance/platform needs. |
| D-09 | No Rust component should be added just to keep the current workspace alive. | A Rust component needs a concrete problem and IPC contract. |

### 1.3 IPC and events

| # | Decision | Notes |
| --- | --- | --- |
| D-10 | There should be one primary backend-to-frontend event/state transport in the first milestone. | Not yet chosen. |
| D-11 | Duplicated state/event types across layers are a defect to reduce, not a normal pattern. | Current Rust crates already duplicate `AppState` and `AppNotification` concepts. |
| D-12 | Unbounded notification channels are not acceptable as the final design. | Backpressure and bounded behavior must be considered. |
| D-13 | UI updates must run on the Qt main thread. | This is a frontend-thread rule for Qt Quick. |

### 1.4 Lifecycle

| # | Decision | Notes |
| --- | --- | --- |
| D-14 | Startup, event handling, and shutdown must be deterministic. | This was a council P0 blocker. |
| D-15 | Shutdown ownership must be defined before more features are added. | The current Rust prototype has a real shutdown-ordering concern. |
| D-16 | The application must pass repeatable start/stop tests. | No feature work should rely on an untested lifecycle. |

### 1.5 Error handling

| # | Decision | Notes |
| --- | --- | --- |
| D-17 | Backend errors should be classified and mapped to frontend-visible status, not leaked raw by default. | Transient/retryable/fatal distinction is required. |
| D-18 | The frontend must degrade gracefully if the backend is unavailable. | Connection loss is a real case, not an edge case to ignore. |

### 1.6 Existing Rust workspace

| # | Decision | Notes |
| --- | --- | --- |
| D-19 | `jarvis-core` may retain useful event/lifecycle concepts but must not become a competing application backend. | |
| D-20 | `jarvis-ui` should be reassessed against the Qt frontend; the GTK placeholder is not the product path. | |
| D-21 | `jarvis-island` may keep the entrypoint concept but must be redesigned around the real runtime. | |
| D-22 | Runtime `cfg!(feature = "gtk4")` backend selection is rejected. | Current committed source still uses this pattern. |
| D-23 | `tokio = { features = ["full"] }` should be narrowed once the runtime design is settled. | |
| D-24 | `ctrlc` is either used for a real shutdown mechanism or removed. | Currently declared but unused for shutdown. |
| D-25 | Declared but unused dependencies should be removed or justified. | |

### 1.7 Licensing and packaging

| # | Decision | Notes |
| --- | --- | --- |
| D-26 | The actual license policy must be resolved before release. | Metadata says MIT, but there is no `LICENSE` file. |
| D-27 | Repository metadata must be corrected. | Current `repository` value is not a proper repository URL. |
| D-28 | A `Cargo.lock` should be committed for this application workspace. | |

## 2. Source conflicts with current committed code

These are explicit conflicts between the frozen decisions and the current `b1f5051` source.

| Conflict | Where | Why it matters |
| --- | --- | --- |
| Documented rejection of runtime `cfg!` backend selection vs current `match cfg!(feature = "gtk4")` | `apps/jarvis-island/src/main.rs` | The code does not match the decision record. |
| Qt/Python product direction vs Rust/GTK workspace shape | whole Rust workspace | The current branch is still organized around a GTK prototype. |
| Deterministic shutdown vs current async forwarding/core/UI split | `apps/jarvis-island/src/main.rs` and `crates/jarvis-core/src/lib.rs` | No single shutdown owner is evident. |
| Single canonical event model vs duplicated types | `crates/jarvis-core/src/events/mod.rs` and `crates/jarvis-ui/src/lib.rs` | Mirror types can drift. |
| Bounded notification preference vs unbounded Tokio channel | `crates/jarvis-core/src/lib.rs` | Current core uses an unbounded channel. |

## 3. Unresolved decisions that still need approval

### 3.1 Frontend/backend boundary

- Which IPC mechanism is used first: local socket, pipes, D-Bus, or another bridge?
- Is the frontend a separate process or an in-process Qt application with a Python worker?

### 3.2 State ownership

- Who owns the canonical state shape for the QML island?
- Does the frontend keep a local mirror, or render from backend state?

### 3.3 Event delivery

- Push, pull, or hybrid for backend-to-frontend updates?
- If push, how are drops and bounded queues handled?

### 3.4 Lifecycle

- Who initiates shutdown?
- What is the shutdown order?
- Is restart/reconnect in scope for the first milestone?

### 3.5 Desktop anchoring

- Is the first milestone a normal window, a layer-shell surface, or both?
- How is top-center positioning achieved?

### 3.6 Rust scope

- Is any current Rust crate worth keeping as a future native component?
- If yes, what narrow responsibility and IPC contract does it own?

### 3.7 Licensing and metadata

- Is the project MIT, all-rights-reserved, or something else?
- What is the correct repository URL metadata?

## 4. Rejected approaches for Phase 0

| Rejected approach | Reason |
| --- | --- |
| Continue building the GTK overlay as the product | Superseded by Qt Quick/QML direction. |
| Add Rust just to preserve the workspace | Not justified without a concrete problem. |
| Keep runtime `cfg!` backend selection | Rejected as ambiguous and inconsistent with the decision record. |
| Expand `jarvis-core` into a competing app backend | Contradicts D-07 and D-19. |
| Add voice, gestures, AI selection, or complex animations now | Out of scope for the first working island. |

## 5. Decision review status

These decisions are recommended, not final.

Before Phase 1 implementation begins, the council should confirm:
- D-01, D-02, D-03, D-04, D-05,
- D-06, D-07, D-08,
- D-10, D-11, D-12, D-13,
- D-14, D-15, D-16,
- D-22, D-26, D-27.

After that, implementation can proceed against a frozen target instead of a moving prototype.
