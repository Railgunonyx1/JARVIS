//! Bounded error log.
//!
//! Ported from `main.js` (`mainErrorLog`, `MAX_MAIN_ERRORS`, `logMainError`).
//! The JavaScript kept the last 200 entries in memory and flushed to
//! `userData/error-log.json` on a 2s debounce, swallowing write failures.
//!
//! Kept here as a pure ring buffer: the *flush* is host work, but deciding what
//! is kept and in what order is policy, and it is the part that can be tested.
//! The original used `shift()` on every append once full, which is O(n) on every
//! log line once the buffer is full — precisely when a crash loop is filling it.

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::time::{SystemTime, UNIX_EPOCH};

/// Matches the Electron build's cap so an existing diagnostics page keeps
/// working unchanged.
pub const MAX_ENTRIES: usize = 200;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Level {
    Debug,
    Info,
    Warn,
    Error,
}

impl Level {
    pub fn as_str(self) -> &'static str {
        match self {
            Level::Debug => "debug",
            Level::Info => "info",
            Level::Warn => "warn",
            Level::Error => "error",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Entry {
    pub level: Level,
    pub message: String,
    pub detail: String,
    /// Unix milliseconds. The JavaScript used `Date.now()`.
    pub timestamp: u64,
}

/// Field caps, ported from the `substring(0, 500)` calls in `logMainError`.
const MAX_FIELD: usize = 500;

pub fn now_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[derive(Debug)]
pub struct ErrorLog {
    entries: VecDeque<Entry>,
    cap: usize,
    /// Bumped on every mutation so a host knows whether to schedule a flush,
    /// replacing the debounce timer that could be lost during a crash.
    dirty: bool,
}

impl Default for ErrorLog {
    fn default() -> Self {
        Self::new(MAX_ENTRIES)
    }
}

impl ErrorLog {
    pub fn new(cap: usize) -> Self {
        Self {
            entries: VecDeque::with_capacity(cap.min(1024)),
            cap: cap.max(1),
            dirty: false,
        }
    }

    pub fn log(&mut self, level: Level, message: impl AsRef<str>, detail: impl AsRef<str>) -> &Entry {
        self.entries.push_back(Entry {
            level,
            message: truncate(message.as_ref()),
            detail: truncate(detail.as_ref()),
            timestamp: now_millis(),
        });
        while self.entries.len() > self.cap {
            self.entries.pop_front();
        }
        self.dirty = true;
        self.entries.back().expect("just pushed")
    }

    pub fn entries(&self) -> impl Iterator<Item = &Entry> {
        self.entries.iter()
    }

    /// Newest first, matching how the downloads list was sorted in the
    /// Electron build (`b.startedAt - a.startedAt`).
    pub fn newest_first(&self) -> Vec<&Entry> {
        self.entries.iter().rev().collect()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn clear(&mut self) {
        self.entries.clear();
        self.dirty = true;
    }

    /// Whether the on-disk copy is behind memory. A host calls `take_dirty`
    /// before flushing and `mark_clean` after, so a failed write keeps the flag
    /// set and the data is retried.
    pub fn take_dirty(&mut self) -> bool {
        std::mem::take(&mut self.dirty)
    }

    pub fn mark_clean(&mut self) {
        self.dirty = false;
    }

    pub fn is_dirty(&self) -> bool {
        self.dirty
    }

    pub fn to_json(&self) -> String {
        // `to_string` on a Vec of serialisable structs cannot fail.
        serde_json::to_string(&self.entries.iter().collect::<Vec<_>>())
            .unwrap_or_else(|_| "[]".to_string())
    }

    /// Replace the contents with what was on disk. A corrupt file is treated as
    /// empty rather than fatal, matching the original's `catch { start fresh }`.
    pub fn load_json(&mut self, raw: &str) -> bool {
        let Ok(parsed) = serde_json::from_str::<Vec<Entry>>(raw) else {
            self.entries.clear();
            self.dirty = false;
            return false;
        };
        self.entries = parsed.into_iter().take(self.cap).collect();
        self.dirty = false;
        true
    }
}

fn truncate(s: &str) -> String {
    if s.chars().count() <= MAX_FIELD {
        return s.to_string();
    }
    s.chars().take(MAX_FIELD).collect()
}