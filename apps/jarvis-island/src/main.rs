//! JARVIS Dynamic Island entry point.
//!
//! First milestone:
//! - initialise structured logging once,
//! - build the core runtime with a notification channel,
//! - start the UI on the main thread when GTK is enabled, otherwise run the
//!   stub on the main thread as well,
//! - keep the process alive so we can wire up the GTK overlay and subsystem
//!   hooks without refactoring the entrypoint later.

use jarvis_core::events::AppState;
use jarvis_core::start;
use jarvis_ui::IslandRunner;
use std::time::Duration;
use tracing::{info, warn};
use tokio::signal;

fn main() -> anyhow::Result<()> {
    // Tracing is initialized exactly once at the application entrypoint.
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "jarvis=info".into()),
        )
        .init();

    info!("JARVIS Dynamic Island starting");

    // When GTK is enabled, this crate runs on the main thread and starts a
    // separate Tokio runtime for background services. When GTK is disabled, we
    // still start a Tokio runtime so core background work can run, but the UI
    // runner stays on the main thread.
    let runtime = tokio::runtime::Runtime::new()?;
    runtime.block_on(async {
        let (notif_tx, notif_rx) = tokio::sync::mpsc::unbounded_channel();

        let core = start(notif_tx)?;

        // The UI backend is selected at compile time through the `gtk4` feature.
        let ui: Box<dyn IslandRunner> = if cfg!(feature = "gtk4") {
            Box::new(jarvis_ui::GtkIslandRunner::new()?)
        } else {
            Box::new(jarvis_ui::stub::StubIslandRunner::new()?)
        };

        // Give the UI its own notification receiver and start it on the main
        // thread. This is the bridge point where async notifications get handed
        // to the UI; the UI implementation is responsible for dispatching them to
        // the correct thread/context in later milestones.
        let ui = ui.with_notification_receiver(notif_rx);

        // Publish an initial collapsed state so the UI knows what to render.
        core.notify(jarvis_core::events::AppNotification::State(AppState::collapsed()));

        // Start the UI. For the GTK build this becomes the main-thread event loop;
        // for the stub build it runs briefly and returns.
        if let Err(err) = ui.run() {
            warn!("island runner exited with error: {err:#}");
        }

        // Keep the process alive with a simple shutdown trigger.
        let shutdown = async {
            signal::ctrl_c().await.is_ok()
        };

        tokio::select! {
            _ = shutdown => {
                info!("shutdown requested");
            }
            _ = tokio::time::sleep(Duration::from_secs(3600)) => {
                // Keep-alive fallback in case the platform suppresses signals.
                info!("shutdown fallback reached");
            }
        }

        info!("JARVIS Dynamic Island stopping");
        Ok(())
    })
}
