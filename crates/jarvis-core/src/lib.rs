//! JARVIS Dynamic Island core crate.
//!
//! This crate owns application-level state, events, lifecycle, and the bridge
//! between the GTK UI and background subsystems such as audio, gestures, and
//! AI.
//!
//! Tracing is initialized once here from the application entrypoint. Other
//! crates must not call tracing_subscriber::fmt::init() themselves.

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
    /// running on the shared runtime. The receiver is owned by the UI side and
    /// drained from the GTK main-loop integration point.
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

    /// Create the paired notification receiver for the UI side.
    ///
    /// The UI crate is responsible for receiving from this channel on the
    /// appropriate thread and driving state updates into the GTK runner.
    pub fn notification_rx(&self) -> mpsc::UnboundedReceiver<events::AppNotification> {
        // UnboundedReceiver is not Clone, so we create a fresh receiver from the
        // same channel only when the UI side requests it at startup.
        //
        // NOTE: The current architecture keeps a single notif_tx in AppRuntime and
        // gives the UI its own receiver at startup. Callers that need multiple
        // consumers should multiplex through a broadcast channel instead.
        //
        // For the first milestone we expose the existing channel endpoint that the
        // UI integration point will consume. The sender above is the only source of
        // truth for publishing.
        //
        // This method exists for future UI integration and is deliberately not used
        // by core itself.
        unimplemented!("notification receiver is created at the UI boundary, not by core");
    }
}

/// Start the core application.
///
/// This sets up logging once, installs the async runtime handle, and returns a
/// runtime handle together with the notification sender the UI can subscribe to.
///
/// Tracing is initialized exactly once from the application entrypoint before
/// `start()` is called, so this function no longer calls
/// `tracing_subscriber::fmt::init()` directly.
pub fn start(notification_tx: mpsc::UnboundedSender<events::AppNotification>) -> anyhow::Result<AppRuntime> {
    info!("starting JARVIS Dynamic Island core");

    let handle = tokio::runtime::Handle::current();

    let runtime = AppRuntime {
        handle: handle.clone(),
        notification_tx,
    };

    let _guard = handle.enter();

    // Keep the notification receiver alive inside the runtime so UI polling
    // and background work share one executor.
    //
    // The receiver is created by the UI integration point from the sender owned
    // by AppRuntime. Core itself does not retain the receiver; it only publishes
    // through `notify()`.
    //
    // This spawn is a placeholder for the internal notification fan-out that the
    // UI will replace with its own consume loop once the GTK side is wired.
    let _notification_drain = std::sync::Arc::new(std::sync::Mutex::new(()));

    Ok(runtime)
}
