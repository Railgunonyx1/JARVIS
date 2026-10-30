//! JARVIS Dynamic Island UI crate.
//!
//! This crate is the placeholder for the native GTK4 + Relm4 overlay.
//!
//! On the current milestone, this crate does not yet assume GTK is available.
//! It exposes the interface the rest of the application will use once GTK is
//! installed, and it keeps the main application loop location clear so we can
//! choose between:
//!
//! - a GTK main-loop driven UI, or
//! - a Tokio-driven app with a GTK window created inside a blocking entrypoint.

#[cfg(feature = "gtk4")]
mod gtk;
#[cfg(feature = "gtk4")]
pub use gtk::GtkIslandRunner;

/// Dynamic Island runner interface.
///
/// The rest of the application should depend on this trait so the UI backend
/// can be swapped between a stub and the real GTK implementation without
/// changing core startup logic.
pub trait IslandRunner: Send + Sync {
    /// Run the island UI until it finishes or is shut down.
    fn run(&self) -> anyhow::Result<()>;

    /// Request the island to show.
    fn show(&self);

    /// Request the island to hide.
    fn hide(&self);

    /// Request the island to expand.
    fn expand(&self);

    /// Request the island to collapse.
    fn collapse(&self);

    /// Update the displayed state.
    fn state(&self, state: jarvis_core::events::AppState);
}
