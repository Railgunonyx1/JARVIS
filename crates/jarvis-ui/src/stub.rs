//! Minimal stub state and runner used when the GTK backend is not enabled.
//!
//! This avoids linking against GTK/Relm4 and `jarvis-core` in the default
//! configuration while keeping the trait and entrypoint stable.
//!
//! The stub runner still owns the notification receiver and drains it on the
//! calling thread so the notification channel is never abandoned.

use super::IslandRunner;

/// Stub application state used only for internal bookkeeping in the non-GTK build.
///
/// The trait itself uses `jarvis_core::events::AppState` as its canonical state
/// type. This struct is a lightweight local placeholder for the stub loop.
#[derive(Debug, Clone, Default)]
pub struct LocalState {
    pub visible: bool,
    pub expanded: bool,
    pub message: String,
}

/// Stub island runner used when the GTK backend is not enabled.
pub struct StubIslandRunner {
    notif_rx: tokio::sync::mpsc::UnboundedReceiver<jarvis_core::events::AppNotification>,
}

impl StubIslandRunner {
    pub fn new() -> anyhow::Result<Self> {
        // The receiver is attached by the entrypoint through
        // `with_notification_receiver`, not here.
        unreachable!("created through IslandRunner::with_notification_receiver");
    }
}

impl IslandRunner for StubIslandRunner {
    fn with_notification_receiver(
        self,
        receiver: tokio::sync::mpsc::UnboundedReceiver<jarvis_core::events::AppNotification>,
    ) -> Self {
        Self { notif_rx: receiver }
    }

    fn run(&self) -> anyhow::Result<()> {
        tracing::info!("running JARVIS Dynamic Island stub (no GTK backend active)");

        let mut notif_rx = self.notif_rx;
        let mut local = LocalState::default();

        loop {
            tokio::select! {
                biased;
                maybe_event = notif_rx.recv() => {
                    if let Some(event) = maybe_event {
                        if let jarvis_core::events::AppNotification::State(state) = event {
                            local.visible = state.visible;
                            local.expanded = state.expanded;
                            local.message = state.message;
                            tracing::info!("stub received state: visible={visible} expanded={expanded} message={message}",
                                visible = local.visible,
                                expanded = local.expanded,
                                message = local.message);
                        }
                    } else {
                        tracing::info!("stub notification channel closed");
                        break;
                    }
                }
                _ = tokio::time::sleep(std::time::Duration::from_secs(60)) => {
                    // Keep the stub alive periodically so the process does not
                    // exit immediately when GTK is disabled.
                    break;
                }
            }
        }

        Ok(())
    }

    fn show(&self) {
        tracing::info!("island show requested");
    }

    fn hide(&self) {
        tracing::info!("island hide requested");
    }

    fn expand(&self) {
        tracing::info!("island expand requested");
    }

    fn collapse(&self) {
        tracing::info!("island collapse requested");
    }

    fn state(&self, state: jarvis_core::events::AppState) {
        tracing::info!("stub state update ignored in current milestone");
        let _ = state;
    }
}
