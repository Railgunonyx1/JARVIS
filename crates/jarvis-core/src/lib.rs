//! JARVIS Dynamic Island core crate.
//!
//! This crate is intended to own application-level state, events, lifecycle,
//! and the bridge between the GTK UI and background subsystems such as audio,
//! gestures, and AI.
//!
//! It is deliberately kept thin for the first milestone. The initial goal is a
//! working async core with structured events and a clear hook for the UI to
//! subscribe to state changes.

pub mod events;
pub mod runtime;

use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

/// Application-wide runtime handle.
///
/// Most background work should be spawned through this rather than creating
/// independent runtimes, so startup ordering and shutdown stay coherent.
pub struct AppRuntime {
    handle: tokio::runtime::Handle,
    _notification_tx: mpsc::UnboundedSender<events::AppNotification>,
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
        if self._notification_tx.send(event).is_err() {
            warn!("UI notification channel dropped");
        }
    }
}

/// Start the core application.
///
/// This sets up logging, installs the async runtime, and returns a runtime
/// handle together with a channel the UI can read from.
pub fn start() -> anyhow::Result<AppRuntime> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "jarvis=info".into()),
        )
        .init();

    info!("starting JARVIS Dynamic Island core");

    let (notif_tx, mut notif_rx) = mpsc::unbounded_channel();

    let handle = tokio::runtime::Handle::current();

    // Keep the notification receiver alive inside the runtime so UI polling
    // and background work share one executor.
    let runtime = AppRuntime {
        handle,
        _notification_tx: notif_tx,
    };

    let _guard = handle.enter();

    tokio::spawn(async move {
        while let Some(event) = notif_rx.recv().await {
            debug!("core notification received internally: {:?}", event);
        }
        info!("core notification loop exited");
    });

    Ok(runtime)
}
