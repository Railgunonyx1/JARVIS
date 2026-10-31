//! JARVIS Dynamic Island entry point.
//!
//! First milestone:
//! - initialise structured logging once,
//! - build the core runtime with a notification channel,
//! - start the UI stub,
//! - keep the process alive so we can wire up the GTK overlay and subsystem
//!   hooks without refactoring the entrypoint later.

use jarvis_core::events::AppState;
use jarvis_core::start;
use jarvis_ui::IslandRunner;
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{info, warn};
use tokio::signal;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Tracing is initialized exactly once at the application entrypoint.
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "jarvis=info".into()),
        )
        .init();

    info!("JARVIS Dynamic Island starting");

    // Create the channel before starting core so core can publish toward the UI.
    let (notif_tx, _notif_rx) = mpsc::unbounded_channel();

    let core = start(notif_tx)?;

    // The UI backend is selected at compile time through the `gtk4` feature on
    // `jarvis-ui`. When that feature is enabled, this crate links the real GTK
    // runner from `jarvis_ui::GtkIslandRunner`. Otherwise it falls back to
    // the built-in stub runner `jarvis_ui::stub::StubIslandRunner`.
    let ui: Box<dyn IslandRunner> = if cfg!(feature = "gtk4") {
        Box::new(jarvis_ui::GtkIslandRunner::new()?)
    } else {
        Box::new(jarvis_ui::stub::StubIslandRunner::new()?)
    };

    // Publish an initial collapsed state so the UI knows what to render.
    core.notify(jarvis_core::events::AppNotification::State(AppState::collapsed()));

    // Start the UI in the background so core can continue to drive state.
    tokio::spawn(async move {
        if let Err(err) = ui.run() {
            warn!("island runner exited with error: {err:#}");
        }
    });

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
}
