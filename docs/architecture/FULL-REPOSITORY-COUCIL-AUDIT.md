# READ-ONLY SNAPSHOT — NOT A LIVE AUDIT

> This document is a point-in-time council review artifact captured during a prior
> read-only review. It is preserved for traceability, not as a current statement of
> repository status, architecture alignment, or implementation readiness.
>
> Do not treat its baseline commit, status notes, verdicts, or "no source changes applied
> during this review" wording as current. The branch may already include later commits,
> including the latest remote commit `0ad5497`, and the current repository state may
> differ from the evidence this document describes.

---

# JARVIS Dynamic Island — Phase 0 Council Review and Verdict

Review type: formal Phase 0 architecture council review and implementation readiness assessment
Branch: `dynamic-island`
Baseline commit: `b1f5051`
Review source: the Phase 0 documents staged in `docs/architecture/`
Real repository: read-only during this review

## 1. Review inputs

The review covered the following Phase 0 documents:

- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/DECISIONS.md`
- `docs/architecture/COMPONENT-BOUNDARIES.md`
- `docs/architecture/IMPLEMENTATION-ROADMAP.md`

These documents are currently staged locally for review and are not yet committed to the branch.

The review also examined the current committed implementation posture on `b1f5051`, including that `apps/jarvis-island/src/main.rs` still uses runtime `cfg!(feature = "gtk4")` backend selection and that the workspace is still shaped around a Rust/GTK prototype.

## 2. Council review roles

The council used independent review perspectives:

1. Systems architect
2. Linux/KDE specialist
3. Backend engineer
4. Reliability engineer
5. Product and performance engineer

## 3. What the council reviewed

### 3.1 Architecture direction

The council reviewed whether the preferred architecture is coherent:

- Qt Quick / QML frontend
- Python backend
- optional narrow Rust
- KDE Wayland on Bazzite first
- explicit interaction activation
- minimal Dynamic Island

**Finding:** The direction is reasonable and preferable to continuing with an unfinished Rust/GTK prototype. The architecture is sound in principle.

**Concern:** The draft documents describe a Qt/Python architecture but the committed source does not demonstrate it. The documents are a proposal, not evidence that the branch has changed.

### 3.2 Component boundaries

The council reviewed the proposed separation of concerns:

- Python backend owns application truth
- Qt Quick / QML frontend owns presentation
- IPC boundary carries state and user actions
- lifecycle and shutdown boundaries are defined as shared concerns with a clear shutdown driver
- error handling is split between backend classification and frontend presentation
- desktop/integration is frontend-led
- Rust is permitted only under a justification test

**Finding:** The boundary model is good and better than the current Rust workspace, which has duplicated types and no single lifecycle owner.

**Concern:** Several boundaries are still intentionally open. That is acceptable for a design document, but it means Phase 1 cannot start from these documents alone without resolving the most blocking open items first.

### 3.3 Technical feasibility

The council reviewed KDE Plasma/Wayland integration, lifecycle, notifications, and voice.

**Findings:**

- KDE Wayland as a first target is reasonable, but a generic Qt window is not automatically a correct Dynamic Island desktop experience.
- Wayland anchoring, focus behavior, input handling, and startup/exit behavior need explicit contracts.
- Lifecycle and notification delivery are still major concerns in the current implementation.
- Voice is correctly treated as later scope.

**Concern:** The documents do not yet commit to enough technical detail to make Phase 1 implementation deterministic. In particular, IPC mechanism, shutdown driver, and Qt main-thread dispatch are not yet fixed.

### 3.4 Migration risks

The council reviewed the transition from the existing GTK4/Rust codebase.

**Findings:**

- The current Rust workspace creates real migration risk because it contains duplicated state/event types, GTK placeholders, and an entrypoint that is not aligned with the proposed architecture.
- `jarvis-core`, `jarvis-ui`, and `jarvis-island` should not be migrated as-is into the Qt/Python architecture without explicit disposition.
- The `cfg!(feature = "gtk4")` runtime selection must be removed from committed code if the Qt/Python direction is final.
- The Tokio unbounded notification channel should not become the recommended final IPC/event design.

**Concern:** Migration risk is high because the current branch is still organized around a GTK prototype. If the Qt/Python direction is final, the Rust workspace must either be repurposed narrowly or stopped, not preserved as-is.

### 3.5 Implementation roadmap

The council reviewed `IMPLEMENTATION-ROADMAP.md`.

**Finding:** The roadmap is correctly ordered. It puts architecture freeze before lifecycle work, lifecycle work before desktop integration, and desktop integration before JARVIS capability integration.

**Concern:** The roadmap correctly lists the current blockers, but the next implementation step still depends on resolving the open IPC, lifecycle, and state-ownership decisions before a smallest working island can be built.

## 4. Council verdicts by area

| Area | Verdict | Reason |
| --- | --- | --- |
| Architecture direction | Approve with revisions | Coherent and preferable to the current prototype, but not yet grounded in committed implementation. |
| Component boundaries | Approve with revisions | Good separation model, but several boundaries remain open and must be closed before Phase 1. |
| Technical feasibility | Approve with revisions | Feasible on KDE Wayland, but requires explicit desktop, lifecycle, and notification contracts. |
| Migration risks | Requires revisions | Current Rust/GTK workspace conflicts with the new direction and must be explicitly rebased or stopped. |
| Implementation roadmap | Approve with revisions | Correctly ordered, but Phase 1 is blocked on unresolved decisions. |
| Phase 1 readiness | Not approved yet | The branch is not yet ready to begin concrete QML/Python implementation from these documents alone. |

## 5. Critical issues

### 5.1 Architecture conflict with committed source

The drafted architecture rejects runtime `cfg!` backend selection and supersedes the GTK4 product direction. The current committed source still uses runtime `cfg!(feature = "gtk4")` selection and is still shaped around a Rust/GTK prototype.

This is not a documentation typo. It is a decision-to-code conflict.

### 5.2 Shutdown deadlock risk in the current implementation

The current entrypoint can wait indefinitely during shutdown because the Tokio notification sender, the forwarding task, and the UI receiver ownership are not governed by one coherent shutdown protocol.

This is a concrete reliability problem in the existing prototype and a direct reason the Qt/Python lifecycle must be defined more strictly.

### 5.3 Unbounded notification channel

The current core uses an unbounded Tokio notification channel. The architecture documents correctly reject unbounded notification channels as the final design. This should not be carried forward as the recommended IPC/event foundation.

### 5.4 Duplicated state/event types

The current crates mirror `AppState` and `AppNotification` concepts. If the Qt/Python architecture is adopted, duplication must be reduced by assigning canonical ownership.

### 5.5 QML/Python not yet demonstrated

The branch does not yet contain a demonstrated QML frontend or a demonstrated Python backend for the Dynamic Island. Therefore the documents describe a future state, not an implemented one.

## 6. Required revisions before approval

### 6.1 Document revisions

The council requires the following before Phase 0 can be approved:

1. Resolve the most blocking open items instead of leaving all of them open:
   - preferred first IPC mechanism and its rationale,
   - preferred primary shutdown driver and shutdown order,
   - preferred Qt main-thread dispatch approach for UI updates,
   - whether the first milestone is one process or two.
2. State explicitly which existing Rust component, if any, is kept and why.
3. State explicitly what happens to the GTK placeholder and stub runner under the new direction.
4. Clarify licensing and repository metadata posture before release work begins.
5. Tighten the acceptance criteria so they are testable from a QML/Python milestone, not just from the current Rust prototype.

### 6.2 Source conflict resolution

The council requires one of the following before implementation advances:

- If the Qt/Python direction is final, remove the conflicting runtime `cfg!` backend selection and stop treating the Rust/GTK prototype as the product path.
- If the direction is not yet final, document that explicitly and do not present Phase 0 as frozen.

## 7. Blockers for Phase 1

The following are blockers for Phase 1 implementation:

1. IPC mechanism not chosen.
2. Lifecycle ownership not finalized.
3. State/event contract ownership not assigned.
4. Qt main-thread dispatch not specified.
5. Committed source still conflicts with the architecture direction.
6. No demonstrated QML frontend or Python backend for the Dynamic Island.

## 8. Acceptance tests required before Phase 1 completion

The council requires the smallest working milestone to prove:

1. Application launches.
2. Island appears in a collapsed pill state.
3. Backend publishes at least one state update that the frontend renders.
4. Island can expand.
5. Island can collapse.
6. One interaction button responds.
7. UI updates after a backend event.
8. Application shuts down cleanly without hanging.
9. Repeated start/stop cycles leave no leftover background work.
10. Behavior is acceptable on KDE Wayland for the first milestone.

These are not optional polish items. They are the minimum proof that the architecture is sound.

## 9. Council verdict

## Verdict: Approve with revisions; Phase 1 not approved yet

The council approves the preferred Qt Quick/QML plus Python architecture direction in principle.

The council does **not** approve the branch as ready for Phase 1 implementation yet.

The Phase 0 documents are useful and better than continuing to build against the unfinished Rust/GTK prototype, but they are still missing several decisions that Phase 1 requires. The current committed source also still conflicts with the proposed architecture.

## 10. Go/no-go for Phase 1

### Go condition

Phase 1 may begin after:

- the blocking open items are resolved or explicitly frozen,
- the architecture documents are revised accordingly,
- the source conflicts are acknowledged or removed,
- the council confirms the first IPC mechanism, shutdown ownership, and Qt main-thread dispatch approach.

### No-go condition

Phase 1 should not begin if:

- the documents remain intentionally open on the most important lifecycle and IPC decisions,
- the committed source is still presented as aligned with the Qt/Python architecture when it is not,
- implementation begins before a smallest working island can be tested for startup, event delivery, and clean shutdown.

## 11. Recommended next steps

1. Resolve the four most blocking open items: IPC mechanism, shutdown driver/order, Qt main-thread dispatch, and one-process-or-two.
2. Revise the Phase 0 documents to reflect those resolutions.
3. Remove or explicitly quarantine the conflicting Rust/GTK prototype assumptions.
4. Define a narrow Rust boundary only if there is a justified need.
5. Build the smallest working QML island and Python backend skeleton against the revised documents.
6. Add lifecycle and shutdown tests before expanding scope.

## 12. Status

Real repository: read-only during this review
Current branch: `dynamic-island`
Current commit: `b1f5051`
Review outcome: approve with revisions
Phase 1 status: not approved yet
Files staged for review: `docs/architecture/*`
Source changes: none applied during this review
Commit/push status: none during this review

---

## Audit snapshot metadata

- Snapshot type: read-only council review document
- Snapshot baseline commit captured in this document: `b1f5051`
- Snapshot reviewer posture: read-only during this review
- Snapshot source archive: `docs/architecture/*`
- Latest repository commit at time of snapshot: `b1f5051`
- Snapshot preservation note: kept verbatim for historical traceability; not updated to reflect later commits
