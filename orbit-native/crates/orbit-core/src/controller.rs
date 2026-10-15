//! `BrowserController`: the seam between Orbit's policy and its engine.
//!
//! This is the most important file in the migration. Everything Orbit decides —
//! when to suspend a tab, whether a permission is allowed, what the user typed
//! — is expressed here as a trait method plus plain data. Nothing below this
//! line knows what WebView2 is; nothing above it does either.
//!
//! That is what makes CEF (or anything else) a Phase 2 decision rather than a
//! rewrite, and it is what lets `orbit-core` be tested without a browser:
//! `FakeController` below is a complete implementation used by the test suite.
//!
//! Every method that can fail returns `Result`. The Electron build returned
//! `{ok: false, error}` strings from handlers and checked them at call sites,
//! which is how "no active guest" quietly became a dead button.

use crate::tabs::TabId;
use serde::{Deserialize, Serialize};
use std::time::Duration;

/// Raised by any backend operation. Kept small on purpose: a browser has a
/// handful of honest failure modes and inventing more is how error handling
/// rots.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ControllerError {
    /// The tab id is not (or no longer) known to this controller.
    NoSuchTab(TabId),
    /// The controller was torn down; the tab is in Restorable, not Active.
    Suspended(TabId),
    /// Navigation was superseded or cancelled by a newer one.
    Superseded,
    /// The engine refused or could not perform the operation.
    Engine(String),
    /// Deliberate refusal by policy, with the reason.
    Denied(String),
}

impl std::fmt::Display for ControllerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ControllerError::NoSuchTab(t) => write!(f, "no such tab: {}", t),
            ControllerError::Suspended(t) => write!(f, "tab is suspended: {}", t),
            ControllerError::Superseded => write!(f, "navigation superseded"),
            ControllerError::Engine(m) => write!(f, "engine error: {}", m),
            ControllerError::Denied(m) => write!(f, "denied: {}", m),
        }
    }
}

impl std::error::Error for ControllerError {}

pub type Result<T> = std::result::Result<T, ControllerError>;

/// Where the engine currently is for a tab.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LoadState {
    Idle,
    Loading,
    Ready,
}

/// A navigation request, after policy has approved it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NavigationRequest {
    pub tab: TabId,
    pub url: String,
    /// Replace rather than push a history entry.
    pub replace: bool,
}

/// Events the host pushes back up the stack. This is the entire read-side of
/// the seam: everything else is pull.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "kebab-case")]
pub enum TabEvent {
    StateChanged {
        tab: TabId,
        state: LoadState,
    },
    TitleChanged {
        tab: TabId,
        title: String,
    },
    UrlChanged {
        tab: TabId,
        url: String,
    },
    FaviconChanged {
        tab: TabId,
        favicon: Option<String>,
    },
    /// The engine wants to navigate somewhere else (a redirect, or a click on
    /// a target the host should confirm).
    NavigationRequested {
        tab: TabId,
        url: String,
    },
    AudioStateChanged {
        tab: TabId,
        audible: bool,
    },
    ProcessGone {
        tab: TabId,
        reason: String,
    },
}

/// Tab lifecycle. Split from navigation because a controller can exist for a
/// tab that is currently suspended, and calling `navigate` on one must fail
/// with `Suspended` rather than magically coming back.
pub trait TabsBackend {
    fn create(&mut self, profile: &ProfileId) -> Result<TabId>;
    fn close(&mut self, tab: &TabId) -> Result<()>;
    fn activate(&mut self, tab: &TabId) -> Result<()>;
    fn active_tab(&self) -> Option<TabId>;
    /// Rebuild the controller for a suspended tab and restore its snapshot.
    fn restore(&mut self, tab: &TabId) -> Result<()>;
    /// Tear the renderer down but keep the tab and its snapshot.
    fn suspend(&mut self, tab: &TabId) -> Result<()>;
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProfileId(pub String);

pub trait NavigationBackend {
    fn goto(&mut self, req: NavigationRequest) -> Result<()>;
    fn back(&mut self, tab: &TabId) -> Result<bool>;
    fn forward(&mut self, tab: &TabId) -> Result<bool>;
    fn reload(&mut self, tab: &TabId, ignore_cache: bool) -> Result<()>;
    fn stop(&mut self, tab: &TabId) -> Result<()>;
    fn can_go_back(&self, tab: &TabId) -> Result<bool>;
}

/// Reading and manipulating page content. Everything here is what JARVIS's
/// `browser.*` tools ultimately need, which is why this trait — not the
/// Electron `webview` tag — is the thing JARVIS is written against.
pub trait PageBackend {
    fn read_text(&mut self, tab: &TabId) -> Result<String>;
    fn screenshot_png(&mut self, tab: &TabId) -> Result<Vec<u8>>;
    /// Evaluate script in the page's main world.
    fn execute(&mut self, tab: &TabId, script: &str) -> Result<serde_json::Value>;
    fn find(&mut self, tab: &TabId, needle: &str) -> Result<Vec<String>>;
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Point {
    pub x: i32,
    pub y: i32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

pub trait InputBackend {
    fn click(&mut self, tab: &TabId, at: Point) -> Result<()>;
    fn type_text(&mut self, tab: &TabId, text: &str) -> Result<()>;
    fn key(&mut self, tab: &TabId, key: &str) -> Result<()>;
    fn scroll(&mut self, tab: &TabId, dy: i32) -> Result<()>;
    /// Element handles, resolved fresh on every use.
    ///
    /// The Electron build's `browser.read` returned indexes that went stale
    /// between the read and the click. A handle that names a live element at
    /// resolution time — and fails loudly otherwise — is the fix, and it lives
    /// behind this trait so the same contract holds for CEF.
    fn find_element(&mut self, tab: &TabId, selector: &str) -> Result<String>;
    fn rect_of(&mut self, tab: &TabId, handle: &str) -> Result<Rect>;
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Download {
    pub id: u64,
    pub tab: TabId,
    pub url: String,
    pub filename: String,
    pub total_bytes: Option<u64>,
    pub received_bytes: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum DownloadState {
    InProgress,
    Completed,
    Cancelled,
    Interrupted,
}

pub trait DownloadsBackend {
    fn cancel(&mut self, id: u64) -> Result<()>;
    fn reveal(&mut self, id: u64) -> Result<()>;
    fn clear_finished(&mut self) -> Result<()>;
}

/// The full engine seam. A backend implements all six; the host owns exactly
/// one. The trait is split so a Phase 2 backend can implement `PageBackend`
/// via CDP and `TabsBackend` natively without a single monolithic type.
pub trait BrowserController: TabsBackend + NavigationBackend + PageBackend + InputBackend
    + DownloadsBackend
{
    /// Human-readable engine identity for diagnostics ("webview2/154.0.0").
    fn engine_version(&self) -> String;

    /// Drain pending engine events. The host owns the event loop, so this is
    /// a pull rather than a callback — it keeps the trait object-safe and the
    /// borrow rules obvious.
    fn drain_events(&mut self) -> Vec<TabEvent>;
}

// ── Fake backend ────────────────────────────────────────────────────────
// Used by the test suite and by `cargo run --example`, so that orbit-core can
// be exercised (and demoed) with no browser and no window.

#[derive(Debug, Default)]
pub struct FakeController {
    pub tabs: Vec<TabId>,
    pub active: Option<TabId>,
    pub suspended: Vec<TabId>,
    pub restored: Vec<TabId>,
    pub last_goto: Option<String>,
    pub last_execute: Option<String>,
    pub reads: Vec<String>,
    seq: u64,
}

impl FakeController {
    pub fn new() -> Self {
        Self::default()
    }
}

impl TabsBackend for FakeController {
    fn create(&mut self, _profile: &ProfileId) -> Result<TabId> {
        self.seq += 1;
        let id = TabId(format!("fake-{}", self.seq));
        self.tabs.push(id.clone());
        if self.active.is_none() {
            self.active = Some(id.clone());
        }
        Ok(id)
    }
    fn close(&mut self, tab: &TabId) -> Result<()> {
        if !self.tabs.contains(tab) {
            return Err(ControllerError::NoSuchTab(tab.clone()));
        }
        self.tabs.retain(|t| t != tab);
        if self.active.as_ref() == Some(tab) {
            self.active = self.tabs.first().cloned();
        }
        Ok(())
    }
    fn activate(&mut self, tab: &TabId) -> Result<()> {
        if self.suspended.contains(tab) {
            return Err(ControllerError::Suspended(tab.clone()));
        }
        if !self.tabs.contains(tab) {
            return Err(ControllerError::NoSuchTab(tab.clone()));
        }
        self.active = Some(tab.clone());
        Ok(())
    }
    fn active_tab(&self) -> Option<TabId> {
        self.active.clone()
    }
    fn restore(&mut self, tab: &TabId) -> Result<()> {
        if !self.tabs.contains(tab) {
            return Err(ControllerError::NoSuchTab(tab.clone()));
        }
        self.suspended.retain(|t| t != tab);
        self.restored.push(tab.clone());
        Ok(())
    }
    fn suspend(&mut self, tab: &TabId) -> Result<()> {
        if !self.tabs.contains(tab) {
            return Err(ControllerError::NoSuchTab(tab.clone()));
        }
        if !self.suspended.contains(tab) {
            self.suspended.push(tab.clone());
        }
        Ok(())
    }
}

impl NavigationBackend for FakeController {
    fn goto(&mut self, req: NavigationRequest) -> Result<()> {
        if self.suspended.contains(&req.tab) {
            return Err(ControllerError::Suspended(req.tab));
        }
        self.last_goto = Some(req.url);
        Ok(())
    }
    fn back(&mut self, _tab: &TabId) -> Result<bool> {
        Ok(false)
    }
    fn forward(&mut self, _tab: &TabId) -> Result<bool> {
        Ok(false)
    }
    fn reload(&mut self, _tab: &TabId, _ignore_cache: bool) -> Result<()> {
        Ok(())
    }
    fn stop(&mut self, _tab: &TabId) -> Result<()> {
        Ok(())
    }
    fn can_go_back(&self, _tab: &TabId) -> Result<bool> {
        Ok(false)
    }
}

impl PageBackend for FakeController {
    fn read_text(&mut self, tab: &TabId) -> Result<String> {
        if self.suspended.contains(tab) {
            return Err(ControllerError::Suspended(tab.clone()));
        }
        Ok("<html><body>fake</body></html>".into())
    }
    fn screenshot_png(&mut self, _tab: &TabId) -> Result<Vec<u8>> {
        Ok(vec![0x89, b'P', b'N', b'G'])
    }
    fn execute(&mut self, tab: &TabId, script: &str) -> Result<serde_json::Value> {
        if self.suspended.contains(tab) {
            return Err(ControllerError::Suspended(tab.clone()));
        }
        self.last_execute = Some(script.to_string());
        Ok(serde_json::Value::Null)
    }
    fn find(&mut self, _tab: &TabId, needle: &str) -> Result<Vec<String>> {
        Ok(if needle.is_empty() { vec![] } else { vec![] })
    }
}

impl InputBackend for FakeController {
    fn click(&mut self, tab: &TabId, _at: Point) -> Result<()> {
        if self.suspended.contains(tab) {
            return Err(ControllerError::Suspended(tab.clone()));
        }
        Ok(())
    }
    fn type_text(&mut self, _tab: &TabId, _text: &str) -> Result<()> {
        Ok(())
    }
    fn key(&mut self, _tab: &TabId, _key: &str) -> Result<()> {
        Ok(())
    }
    fn scroll(&mut self, _tab: &TabId, _dy: i32) -> Result<()> {
        Ok(())
    }
    fn find_element(&mut self, _tab: &TabId, selector: &str) -> Result<String> {
        Ok(format!("handle:{}", selector))
    }
    fn rect_of(&mut self, _tab: &TabId, _handle: &str) -> Result<Rect> {
        Ok(Rect {
            x: 0,
            y: 0,
            width: 0,
            height: 0,
        })
    }
}

impl DownloadsBackend for FakeController {
    fn cancel(&mut self, _id: u64) -> Result<()> {
        Ok(())
    }
    fn reveal(&mut self, _id: u64) -> Result<()> {
        Ok(())
    }
    fn clear_finished(&mut self) -> Result<()> {
        Ok(())
    }
}

impl BrowserController for FakeController {
    fn engine_version(&self) -> String {
        "fake/0".into()
    }
    fn drain_events(&mut self) -> Vec<TabEvent> {
        Vec::new()
    }
}

/// Engine-advertised behaviour the host must respect.
///
/// The Electron build had no such struct, which is why "does this engine
/// support blocking?" was answered by hoping. A backend declares its own
/// limits at construction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EngineCapabilities {
    /// Can intercept and cancel/redirect requests before they leave.
    pub request_interception: bool,
    /// Can rewrite response headers.
    pub response_header_rewrite: bool,
    /// Can freeze a background renderer without destroying it.
    pub lifecycle_freeze: bool,
    /// Supports multiple profiles in one process collection.
    pub multi_profile: bool,
    /// Supports installing Chrome-format extensions.
    pub extensions: bool,
    pub name: String,
    pub version: String,
}

impl EngineCapabilities {
    /// What WebView2 can actually do. `extensions: false` is not a bug in this
    /// table — WebView2 has no Chrome extension support at all, and Orbit's
    /// "Extension Store" is a web page that opens store links, so nothing
    /// regresses today. Recording it here means the moment someone tries to
    /// ship real extensions, it fails loudly at startup instead of silently
    /// doing nothing.
    pub fn webview2() -> Self {
        Self {
            request_interception: true,
            response_header_rewrite: true,
            lifecycle_freeze: false,
            multi_profile: true,
            extensions: false,
            name: "webview2".to_string(),
            version: "154".into(),
        }
    }
}

/// Host-side timer policy, exposed so the UI can explain itself.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Budget {
    pub throttle_after: Duration,
    pub suspend_after: Duration,
}