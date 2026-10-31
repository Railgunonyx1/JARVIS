//! JARVIS Dynamic Island core crate.
//!
//! This crate owns application-level state, events, lifecycle, and the bridge
//! between the GTK UI and background subsystems such as audio, gestures, and
//! AI.
//!
//! Tracing is initialized once at the application entrypoint. Other crates must
//! not call tracing_subscriber::fmt::init() themselves.

pub mod events;
pub mod runtime;

use tokio::sync::mpsc;
use tracing::{info, warn};

/// Application-wide runtime handle.
///
/// Most background work should be spawned through this rather than creating
/// independent runtimes, so startup ordering and shutdown stay coherent.
pub struct AppRuntime {
    handle: tokio::runtime::Handle,
    /// Unbounded channel used by core to publish notifications toward the UI.
    ///
    /// The sender is stored here so core can emit notifications from any task
    /// running on the shared runtime. The receiver is created once at startup and
    /// passed to the UI integration point.
    notification_tx: mpsc::UnboundedSender<events::AppNotification>,
}

impl AppRuntime {
    pub fn handle(&self) -> tokio::runtime::Handle {
        self.handle.clone()
    }

    /// Send a notification to the UI without blocking.
    ///
    /// This is the primary asynchronous output channel from core to UI during
    /// the first milestone. UI-driven input comes back through commands and
    /// explicit calls, not through this channel.
    pub fn notify(&self, event: events::AppNotification) {
        if self.notification_tx.send(event).is_err() {
            warn!("UI notification channel dropped");
        }
    }
}

/// Start the core application.
///
/// This sets up the async runtime handle and returns a runtime handle together
/// with the notification sender the UI can subscribe to.
///
/// Tracing is initialized exactly once from the application entrypoint before
/// `start()` is called, so this function does not initialize tracing itself.
pub fn start(notification_tx: mpsc::UnboundedSender<events::AppNotification>) -> anyhow::Result<AppRuntime> {
    info!("starting JARVIS Dynamic Island core");

    let handle = tokio::runtime::Handle::current();

    let runtime = AppRuntime {
        handle: handle.clone(),
        notification_tx,
    };

    let _guard = handle.enter();

    // Background work and UI notification consumption share one executor once the
    // UI integration point drains the receiver on the appropriate thread.
    //
    // For the first milestone the receiver is owned by the UI side. Core only
    // publishes through `notify()`.

    Ok(runtime)
}
