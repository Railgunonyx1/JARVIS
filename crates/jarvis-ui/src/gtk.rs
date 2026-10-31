//! GTK4 + Relm4 Dynamic Island implementation.
//!
//! This module is compiled only when the `gtk4` feature is enabled. It is the
//! intended place for:
//!
//! - layer-shell anchoring for a top-centre overlay,
//! - collapsed/expanded presentation,
//! - transparency and input handling,
//! - monitor-change and display-scaling handling.
//!
//! The GTK backend is currently a scaffold. The Rust lifecycle glue is in place,
//! but the actual overlay window, layer-shell wiring, and main-loop integration
//! are not implemented yet.

use crate::IslandRunner;

pub struct GtkIslandRunner {
    notif_rx: tokio::sync::mpsc::UnboundedReceiver<jarvis_core::events::AppNotification>,
}

impl GtkIslandRunner {
    pub fn new() -> anyhow::Result<Self> {
        // The receiver is attached by the entrypoint through
        // `with_notification_receiver`, not here.
        unreachable!("created through IslandRunner::with_notification_receiver");
    }
}

impl IslandRunner for GtkIslandRunner {
    fn with_notification_receiver(
        self,
        receiver: tokio::sync::mpsc::UnboundedReceiver<jarvis_core::events::AppNotification>,
    ) -> Self {
        Self { notif_rx: receiver }
    }

    fn run(&self) -> anyhow::Result<()> {
        // When GTK is enabled, this should become the GTK main-thread event loop.
        // For the current milestone we cannot start a real GTK loop because GTK is
        // not wired yet, so we bail with a clear message.
        anyhow::bail!("GTK4 backend is not wired yet. Enable the gtk4 feature and implement the layer-shell window.");
    }

    fn show(&self) {
        tracing::info!("gtk island show requested");
    }

    fn hide(&self) {
        tracing::info!("gtk island hide requested");
    }

    fn expand(&self) {
        tracing::info!("gtk island expand requested");
    }

    fn collapse(&self) {
        tracing::info!("gtk island collapse requested");
    }

    fn state(&self, state: jarvis_core::events::AppState) {
        tracing::info!(?state, "gtk island state updated");
        let _ = state;
    }
}
