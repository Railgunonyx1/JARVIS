//! GTK4 + Relm4 Dynamic Island implementation.
//!
//! This module is compiled only when the `gtk4` feature is enabled. It is the
//! intended place for:
//!
//! - layer-shell anchoring for a top-centre overlay,
//! - collapsed/expanded presentation,
//! - transparency and input handling,
//! - monitor-change and display-scaling handling.

use crate::IslandRunner;
use crate::stub::AppState;

pub struct GtkIslandRunner {
    // In the first real GTK milestone, hold the window and layer-shell state
    // here. For now this is intentionally a scaffold.
}

impl GtkIslandRunner {
    pub fn new() -> anyhow::Result<Self> {
        anyhow::bail!(
            "GTK4 backend is not wired yet. Enable the gtk4 feature and implement              the layer-shell window."
        );
    }
}

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

    fn state(&self, _state: AppState) {
        tracing::info!("gtk island state updated");
    }
}
