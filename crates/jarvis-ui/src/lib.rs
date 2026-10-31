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
//!
//! The GTK backend is optional. When the `gtk4` feature is enabled, this crate
//! compiles the real GTK runner and links against GTK/Relm4. Otherwise only
//! the trait and the stub runner are available.

mod gtk;

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
    fn state(&self, state: crate::stub::AppState);
}

pub mod stub {
    //! Minimal stub state type and runner used when the GTK backend is not
    //! enabled.
    //!
    //! This avoids linking against GTK/Relm4 and `jarvis-core` in the default
    //! configuration while keeping the trait and entrypoint stable.

    use super::IslandRunner;

    #[derive(Debug, Clone, Default)]
    pub struct AppState {
        pub visible: bool,
        pub expanded: bool,
        pub message: String,
    }

    /// Stub island runner used when the GTK backend is not enabled.
    pub struct StubIslandRunner;

    impl StubIslandRunner {
        pub fn new() -> anyhow::Result<Self> {
            Ok(Self)
        }
    }

    impl IslandRunner for StubIslandRunner {
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

        fn state(&self, _state: crate::stub::AppState) {
            tracing::info!("island state updated (stub)");
        }
    }
}

#[cfg(feature = "gtk4")]
pub mod events {
    //! Re-export of core event types when the GTK backend is enabled.
    //!
    //! The GTK runner and any UI-side state handling depend on these types only
    //! when the `gtk4` feature is active, which is when `jarvis-core` is linked
    //! and the real GTK module is compiled.

    pub use jarvis_core::events::{AppNotification, AppState};
}
