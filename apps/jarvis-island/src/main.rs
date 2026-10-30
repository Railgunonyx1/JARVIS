//! JARVIS Dynamic Island entry point.
//!
//! First milestone:
//! - initialise structured logging,
//! - build the core runtime,
//! - start the UI stub,
//! - keep the process alive so we can wire up the GTK overlay and subsystem
//!   hooks without refactoring the entrypoint later.

use jarvis_core::events::AppState;
use jarvis_core::start;
use jarvis_ui::IslandRunner;
use std::time::Duration;
use tracing::{info, warn};
use tokio::signal;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "jarvis=info".into()),
        )
        .init();

    info!("JARVIS Dynamic Island starting");

    let core = start()?;

    // The UI backend is selected through the feature flag on jarvis-ui.
    // Once GTK layer-shell is wired, we will switch this from the stub to the
    // real GTK runner.
    let ui = jarvis_ui::GtkIslandRunner::new()?;
    let ui = Box::new(ui);

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
