//! `orbit-core` — Orbit's browser policy, with no browser in it.
//!
//! Everything that *decides* lives here: which URLs are allowed, which origins
//! hold which permission, when a tab is throttled or suspended, what a session
//! snapshot contains, and what the engine is allowed to be asked for. Nothing
//! that *performs* lives here.
//!
//! That split is the whole point. The Electron build mixed the two in
//! `main.js`, which is why its policy could only be tested by launching a
//! browser. Here `cargo test` covers every branch on a headless machine,
//! including the SSRF filter, the permission defaults and the tab sweep.
//!
//! ```
//! use orbit_core::{NetworkPolicy, Decision, BlockReason};
//!
//! // A page subresource aimed at the router is blocked; a user typing it is not.
//! let p = NetworkPolicy::default();
//! assert_eq!(
//!     p.decide("http://192.168.1.1/admin", false, false),
//!     Decision::Block(BlockReason::PrivateNetwork)
//! );
//! assert_eq!(
//!     p.decide("http://192.168.1.1/admin", true, false),
//!     Decision::Allow
//! );
//! ```

pub mod controller;
pub mod error_log;
pub mod permissions;
pub mod pin;
pub mod tabs;
pub mod url;

pub use controller::{
    BrowserController, ControllerError, DownloadsBackend, EngineCapabilities, FakeController,
    InputBackend, NavigationBackend, PageBackend, ProfileId, TabsBackend, TabEvent,
};
pub use error_log::{ErrorLog, Entry, Level};
pub use permissions::{Grant, Permission, PermissionDecision, PermissionStore};
pub use tabs::{LifecycleAction, LifecyclePolicy, LifecycleState, RestorableState, Tab, TabId, TabRegistry};
pub use url::{parse, BlockReason, Decision, NetworkPolicy, ParsedUrl, UrlError};

/// The engine Orbit is built against, and what it can do.
pub const ENGINE: &str = "webview2";

/// Name shown in the UI and in diagnostics.
pub const PRODUCT: &str = "JARVIS Orbit";