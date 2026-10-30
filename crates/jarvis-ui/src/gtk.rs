//! GTK4 + Relm4 Dynamic Island implementation.
//!
//! This module is compiled only when the `gtk4` feature is enabled. It is the
//! intended place for:
//!
//! - layer-shell anchoring for a top-centre overlay,
//! - collapsed/expanded presentation,
//! - transparency and input handling,
//! - monitor-change and display-scaling handling.

#[cfg(feature = "gtk4")]
use crate::IslandRunner;
#[cfg(feature = "gtk4")]
use jarvis_core::events::{AppNotification, AppState};

#[cfg(feature = "gtk4")]
pub struct GtkIslandRunner {
    // In the first real GTK milestone, hold the window and layer-shell state
    // here. For now this is intentionally a scaffold.
}

#[cfg(feature = "gtk4")]
impl GtkIslandRunner {
    pub fn new() -> anyhow::Result<Self> {
        anyhow::bail!(
            "GTK4 backend is not wired yet. Enable the gtk4 feature and implement \
             the layer-shell window."
        );
    }
}

#[cfg(feature = "gtk4")]
impl IslandRunner for GtkIslandRunner {
    fn run(&self) -> anyhow::Result<()> {
        anyhow::bail!("GTK runner not implemented yet")
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

    fn state(&self, state: AppState) {
        tracing::info!(?state, "gtk island state updated");
    }
}

#[cfg(not(feature = "gtk4"))]
/// Placeholder used when GTK is not available.
pub struct GtkIslandRunner;

#[cfg(not(feature = "gtk4"))]
impl GtkIslandRunner {
    pub fn new() -> anyhow::Result<Self> {
        Ok(Self)
    }
}

#[cfg(not(feature = "gtk4"))]
impl IslandRunner for GtkIslandRunner {
    fn run(&self) -> anyhow::Result<()> {
        tracing::info!("running JARVIS Dynamic Island stub (no GTK backend active)");
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

    fn state(&self, state: AppState) {
        tracing::info!(?state, "island state updated");
    }
}
