//! Site permissions: default-deny, allowlist wins.
//!
//! Ported from `main.js` (`PERMISSION_ALLOWLIST`, `isAllowedPermission`, the
//! `permissions:*` handlers) and `preload.js`'s `orbit.permissions` surface.
//!
//! The posture is deliberately aggressive and unchanged from the original:
//! a permission is granted only if a user-visible grant put it in the list.
//! Anything else — including a request from a site the user has never
//! approved — is denied. Note that JARVIS is a separate principal and is
//! *not* routed through this list; see `Permission::` below.

use serde::{Deserialize, Serialize};

/// A permission Orbit knows how to gate. Kept closed on purpose: an unknown
/// string from the page must not fall through to "allow".
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Permission {
    Notifications,
    Microphone,
    Camera,
    Geolocation,
    ClipboardRead,
    Midi,
    MidiSysex,
    PointerLock,
    Fullscreen,
    Autoplay,
    OpenExternal,
    ScreenCapture,
    /// Wildcard grant for an origin: everything Orbit can gate.
    All,
}

impl Permission {
    pub fn parse(raw: &str) -> Option<Self> {
        Some(match raw {
            "notifications" => Permission::Notifications,
            "media" | "microphone" => Permission::Microphone,
            "camera" => Permission::Camera,
            "geolocation" => Permission::Geolocation,
            "clipboard-read" => Permission::ClipboardRead,
            "midi" => Permission::Midi,
            "midi-sysex" => Permission::MidiSysex,
            "pointer-lock" => Permission::PointerLock,
            "fullscreen" => Permission::Fullscreen,
            "autoplay" => Permission::Autoplay,
            "openExternal" | "open-external" => Permission::OpenExternal,
            "screen-capture" | "display-capture" => Permission::ScreenCapture,
            "*" | "all" => Permission::All,
            _ => return None,
        })
    }
}

/// One origin's grants.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Grant {
    pub origin: String,
    pub permissions: Vec<String>,
}

impl Grant {
    /// Mirrors the JS `e.permissions.includes("*") || e.permissions.includes(p)`.
    pub fn allows(&self, permission: Permission) -> bool {
        self.permissions.iter().any(|p| {
            p == "*" || Permission::parse(p).map(|x| x == permission).unwrap_or(false)
        })
    }
}

/// The decision returned to the WebView2 `PermissionRequested` handler.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionDecision {
    Allow,
    /// Deny silently. Orbit's existing posture: no prompt, no grant.
    Deny,
}

/// The allowlist. Deny-by-default: absent means denied.
#[derive(Debug, Clone, Default)]
pub struct PermissionStore {
    grants: Vec<Grant>,
}

impl PermissionStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn from(grants: Vec<Grant>) -> Self {
        let mut s = Self::new();
        for g in grants {
            s.allow(&g.origin, g.permissions.clone());
        }
        s
    }

    /// Grant one or more permissions to an origin. Unknown permission strings
    /// are rejected rather than stored, so a typo cannot silently widen access.
    pub fn allow(&mut self, origin: &str, permissions: Vec<String>) {
        for raw in permissions {
            if Permission::parse(&raw).is_none() {
                continue;
            }
            match self.grants.iter_mut().find(|g| g.origin == origin) {
                Some(g) => {
                    if !g.permissions.contains(&raw) {
                        g.permissions.push(raw);
                    }
                }
                None => self.grants.push(Grant {
                    origin: origin.to_string(),
                    permissions: vec![raw],
                }),
            }
        }
    }

    /// Revoke one permission, or every permission for the origin when `None`.
    ///
    /// The JS original left an empty `Grant` behind in some paths; an empty
    /// grant is dead state that later reads must keep special-casing, so the
    /// entry is dropped entirely.
    pub fn revoke(&mut self, origin: &str, permission: Option<&str>) {
        let Some(idx) = self.grants.iter().position(|g| g.origin == origin) else {
            return;
        };
        match permission {
            Some(p) => {
                self.grants[idx].permissions.retain(|x| x != p);
                if self.grants[idx].permissions.is_empty() {
                    self.grants.remove(idx);
                }
            }
            None => {
                self.grants.remove(idx);
            }
        }
    }

    /// The decision for a request. Default deny.
    pub fn decide(&self, origin: &str, permission: Permission) -> PermissionDecision {
        let granted = self
            .grants
            .iter()
            .find(|g| g.origin == origin)
            .map(|g| g.allows(permission))
            .unwrap_or(false);
        if granted {
            PermissionDecision::Allow
        } else {
            PermissionDecision::Deny
        }
    }

    pub fn list(&self) -> Vec<Grant> {
        self.grants.clone()
    }

    pub fn is_empty(&self) -> bool {
        self.grants.is_empty()
    }
}