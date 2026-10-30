//! Structured application events and notifications.

use serde::{Deserialize, Serialize};

/// State of the Dynamic Island presentation.
///
/// The UI reads this and renders the appropriate collapsed, expanded, listening,
/// processing, or error state. Core publishes updates; the UI discovers changes
/// through the notification channel or by polling [AppState] on demand.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AppState {
    pub visible: bool,
    pub expanded: bool,
    pub mode: Mode,
    pub message: String,
    pub error: Option<String>,
}

impl AppState {
    pub fn collapsed() -> Self {
        Self {
            visible: true,
            expanded: false,
            mode: Mode::Idle,
            message: "JARVIS".into(),
            error: None,
        }
    }

    pub fn listening() -> Self {
        Self {
            visible: true,
            expanded: false,
            mode: Mode::Listening,
            message: "JARVIS\nListening".into(),
            error: None,
        }
    }

    pub fn expanded_prompt() -> Self {
        Self {
            visible: true,
            expanded: true,
            mode: Mode::Idle,
            message: "How can I help?".into(),
            error: None,
        }
    }
}

/// High-level presentation mode.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum Mode {
    Idle,
    Listening,
    Processing,
    Response,
    Error,
}

impl Default for Mode {
    fn default() -> Self {
        Self::Idle
    }
}

/// Notifications emitted by core toward the UI.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AppNotification {
    /// Application state changed.
    State(AppState),
    /// Core decided the island should be shown or hidden.
    Visibility(bool),
    /// Core decided the island should be expanded or collapsed.
    Expand(bool),
    /// A transient message to display.
    Message(String),
    /// An error to display.
    Error(String),
}

impl AppNotification {
    pub fn state(mut self, state: AppState) -> Self {
        self = Self::State(state);
        self
    }
}
