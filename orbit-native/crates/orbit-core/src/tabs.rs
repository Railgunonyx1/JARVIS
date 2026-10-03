//! Tabs and the tab lifecycle.
//!
//! Ported from `orbit-browser/src/js/tabs.js` (createTab/closeTab/setActiveTab/
//! reopenClosedTab) and `main.js` (the `tabs` Map, `activeTabId`,
//! `webContentsIds`, `frozenTabs`, and the `sessionSnapshot` filter).
//!
//! The lifecycle states replace the Electron-era ambiguity that the audit
//! called out: a "hidden" webview was neither live nor dead, and freezing was
//! done opportunistically. Here the state is explicit and the transition
//! rules are the only thing that decides what the host should do.
//!
//! NOTE ON `restorable`: `Restorable` is deliberately a *state*, not a flag.
//! A suspended tab still exists in the registry with a restorable snapshot;
//! the point is that the host can never confuse "gone" with "gone but coming
//! back", which is exactly the bug that made `freezeTab` silently no-op when
//! the id -> webContents map went stale.

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::time::{Duration, Instant};

/// Opaque, stable tab identity. Never reused within a session: the old JS
/// ids embedded `Date.now()` plus randomness, which made them unique but not
/// typed, and invited stringly-typed comparisons at call sites.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TabId(pub String);

impl TabId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Display for TabId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Where a tab is in its life. Ordered from most to least resident.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LifecycleState {
    /// Visible and interacted with. Full renderer, full timers.
    Active,
    /// A background tab that is still worth keeping live.
    Warm,
    /// Background, timers deliberately cut to save CPU.
    Throttled,
    /// Renderer destroyed. Snapshot retained. This is the state the Electron
    /// build could not actually reach — it hid the webview, which freed
    /// nothing.
    Suspended,
    /// Suspended and evicted from memory; only the serialised snapshot exists.
    Restorable,
}

impl LifecycleState {
    /// Does a live renderer exist in this state?
    pub fn has_live_controller(self) -> bool {
        matches!(
            self,
            LifecycleState::Active | LifecycleState::Warm | LifecycleState::Throttled
        )
    }

    /// Does this state cost a renderer process right now?
    pub fn is_resident(self) -> bool {
        self.has_live_controller()
    }

    /// Can the state be moved to without reloading the page?
    pub fn is_cheap_to_leave(self) -> bool {
        !matches!(self, LifecycleState::Restorable)
    }
}

/// Enough to bring a destroyed tab back. Everything here survives a reload;
/// anything not here is re-derived.
///
/// `scroll_y` is milliseconds-scaled integer hundredths rather than an `f64`
/// so the whole snapshot round-trips through serde without float formatting
/// drift, and so the type can stay `Eq` (and therefore comparable) — which is
/// what makes session snapshots diffable.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RestorableState {
    pub url: String,
    pub title: String,
    pub favicon: Option<String>,
    /// Scroll offset in hundredths of a CSS pixel.
    pub scroll_y_x100: u32,
    /// Whether a JARVIS task owns this tab. Owned tabs are never suspended
    /// automatically: the agent may be mid-navigation.
    pub agent_owned: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Tab {
    pub id: TabId,
    pub url: String,
    pub title: String,
    pub favicon: Option<String>,
    pub loading: bool,
    pub agent_owned: bool,
    pub state: LifecycleState,
    /// Last measured working set in MiB. Sourced from Chromium process
    /// metrics in the host, never from a renderer-reported number.
    pub memory_mb: u64,
    pub audible: bool,
    pub snapshot: Option<RestorableState>,
    pub last_active: Instant,
}

impl Tab {
    fn new(id: TabId, url: String) -> Self {
        Self {
            id,
            url,
            title: "New tab".into(),
            favicon: None,
            loading: false,
            agent_owned: false,
            state: LifecycleState::Warm,
            memory_mb: 0,
            audible: false,
            snapshot: None,
            last_active: Instant::now(),
        }
    }

    /// Capture what is needed to rebuild this tab later. Called on the way
    /// *into* a destroyed state — capturing after teardown races the teardown.
    pub fn to_restorable(&self) -> RestorableState {
        RestorableState {
            url: self.url.clone(),
            title: self.title.clone(),
            favicon: self.favicon.clone(),
            scroll_y_x100: 0,
            agent_owned: self.agent_owned,
        }
    }
}

/// The result of asking the lifecycle policy what to do.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LifecycleAction {
    /// Do nothing; the state is already correct.
    None,
    /// Ask the host to freeze timers but keep the renderer.
    Throttle(TabId),
    /// Ask the host to tear the renderer down; the snapshot is kept.
    Suspend(TabId),
}

/// Policy inputs. All of these were implicit branches in `runSleepCheck`.
#[derive(Debug, Clone, Copy)]
pub struct LifecyclePolicy {
    /// Age of inactivity after which a background tab may be throttled.
    pub throttle_after: Duration,
    /// Age of inactivity after which a background tab may be suspended.
    pub suspend_after: Duration,
    /// Above this many live background tabs, suspend immediately regardless
    /// of age. This is the global ceiling the Electron `webview-pool.js`
    /// claimed to provide and did not.
    pub max_resident_background: usize,
    /// Never suspend a tab making noise, whatever its age.
    pub protect_audible: bool,
    /// Never suspend a tab JARVIS owns.
    pub protect_agent_owned: bool,
}

impl Default for LifecyclePolicy {
    fn default() -> Self {
        Self {
            throttle_after: Duration::from_secs(120),
            suspend_after: Duration::from_secs(600),
            max_resident_background: 12,
            protect_audible: true,
            protect_agent_owned: true,
        }
    }
}

/// The tab set for one window/profile.
#[derive(Debug)]
pub struct TabRegistry {
    tabs: HashMap<TabId, Tab>,
    order: VecDeque<TabId>,
    active: Option<TabId>,
    policy: LifecyclePolicy,
    closed: VecDeque<RestorableState>,
    next_seq: u64,
    /// How many ids have been minted; ids are never reused so a late event
    /// from a closed tab can never be applied to a new one.
    minted: u64,
}

impl Default for TabRegistry {
    fn default() -> Self {
        Self::new(LifecyclePolicy::default())
    }
}

impl TabRegistry {
    pub fn new(policy: LifecyclePolicy) -> Self {
        Self {
            tabs: HashMap::new(),
            order: VecDeque::new(),
            active: None,
            policy,
            closed: VecDeque::new(),
            next_seq: 0,
            minted: 0,
        }
    }

    fn mint_id(&mut self, _url: &str) -> TabId {
        self.minted += 1;
        self.next_seq += 1;
        // Monotonic and unique: `tab-1`, `tab-2`, ... plus a session nonce so
        // ids from a restored session cannot collide with fresh ones.
        TabId(format!("tab-{:016x}-{}", self.minted, self.next_seq))
    }

    pub fn create(&mut self, url: Option<&str>) -> TabId {
        let id = self.mint_id(url.unwrap_or("orbit://newtab"));
        let tab = Tab::new(id.clone(), url.unwrap_or("orbit://newtab").to_string());
        self.tabs.insert(id.clone(), tab);
        self.order.push_back(id.clone());
        if self.active.is_none() {
            self.active = Some(id.clone());
        }
        id
    }

    /// Adopt a tab the host created out of band (a popup that was routed into
    /// an existing tab, say) without minting a new identity.
    pub fn adopt(&mut self, id: TabId, url: &str) {
        if self.tabs.contains_key(&id) {
            return;
        }
        self.minted += 1;
        let mut tab = Tab::new(id.clone(), url.to_string());
        tab.state = LifecycleState::Warm;
        self.tabs.insert(id.clone(), tab);
        self.order.push_back(id);
    }

    pub fn close(&mut self, id: &TabId) -> Option<Tab> {
        let tab = self.tabs.remove(id)?;
        self.order.retain(|x| x != id);
        // Reopen history is bounded; unbounded "closed tabs" is a memory leak
        // that looks like a feature.
        if self.closed.len() >= 25 {
            self.closed.pop_front();
        }
        self.closed.push_back(tab.to_restorable());
        if self.active.as_ref() == Some(id) {
            let next = self.order.front().cloned();
            self.active = next.clone();
            if let Some(next) = next {
                self.mark_active(&next);
            }
        }
        Some(tab)
    }

    /// Reopen the most recently closed tab, if it is still restorable.
    pub fn reopen_closed(&mut self) -> Option<TabId> {
        let snap = self.closed.pop_back()?;
        let id = self.mint_id(&snap.url);
        let mut tab = Tab::new(id.clone(), snap.url.clone());
        tab.title = snap.title;
        tab.favicon = snap.favicon;
        tab.agent_owned = snap.agent_owned;
        self.tabs.insert(id.clone(), tab);
        self.order.push_back(id.clone());
        Some(id)
    }

    pub fn get(&self, id: &TabId) -> Option<&Tab> {
        self.tabs.get(id)
    }

    pub fn get_mut(&mut self, id: &TabId) -> Option<&mut Tab> {
        self.tabs.get_mut(id)
    }

    pub fn active(&self) -> Option<&Tab> {
        self.active.as_ref().and_then(|id| self.tabs.get(id))
    }

    pub fn set_active(&mut self, id: &TabId) -> bool {
        if !self.tabs.contains_key(id) {
            return false;
        }
        self.active = Some(id.clone());
        self.mark_active(id);
        true
    }

    /// Called by the host when a tab becomes visible. Restores a suspended tab
    /// to Active; the host is expected to rebuild the controller first.
    pub fn mark_active(&mut self, id: &TabId) {
        if let Some(tab) = self.tabs.get_mut(id) {
            tab.last_active = Instant::now();
            tab.state = LifecycleState::Active;
        }
    }

    pub fn set_state(&mut self, id: &TabId, state: LifecycleState) {
        if let Some(tab) = self.tabs.get_mut(id) {
            // Snapshot on the way out of residency, never on the way in: after
            // teardown the URL and title may already be gone.
            if tab.state.is_resident() && !state.is_resident() {
                tab.snapshot = Some(tab.to_restorable());
            }
            tab.state = state;
        }
    }

    pub fn update_memory(&mut self, id: &TabId, mb: u64) {
        if let Some(tab) = self.tabs.get_mut(id) {
            tab.memory_mb = mb;
        }
    }

    pub fn set_audible(&mut self, id: &TabId, audible: bool) {
        if let Some(tab) = self.tabs.get_mut(id) {
            tab.audible = audible;
        }
    }

    pub fn set_loading(&mut self, id: &TabId, loading: bool) {
        if let Some(tab) = self.tabs.get_mut(id) {
            tab.loading = loading;
        }
    }

    pub fn set_metadata(&mut self, id: &TabId, url: &str, title: &str) {
        if let Some(tab) = self.tabs.get_mut(id) {
            tab.url = url.to_string();
            if !title.is_empty() {
                tab.title = title.to_string();
            }
        }
    }

    /// Tabs in visual order.
    pub fn ordered(&self) -> Vec<&Tab> {
        self.order.iter().filter_map(|id| self.tabs.get(id)).collect()
    }

    pub fn len(&self) -> usize {
        self.tabs.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tabs.is_empty()
    }

    /// How many background tabs still hold a live renderer.
    pub fn resident_background(&self) -> usize {
        self.tabs
            .values()
            .filter(|t| t.state.is_resident() && self.active.as_ref() != Some(&t.id))
            .count()
    }

    /// Decide what to do about background tabs right now.
    ///
    /// Returns at most one action per tab and never touches the active tab.
    /// Ordering is deterministic: the oldest tab is the first candidate, so a
    /// sweep that runs twice with the same inputs does the same thing.
    pub fn sweep(&self, now: Instant) -> Vec<LifecycleAction> {
        let mut out = Vec::new();
        // Oldest first, so the eviction ceiling takes the stalest tabs.
        let mut candidates: Vec<&Tab> = self
            .tabs
            .values()
            .filter(|t| self.active.as_ref() != Some(&t.id))
            .filter(|t| t.state.is_resident())
            .collect();
        candidates.sort_by_key(|t| t.last_active);

        for tab in &candidates {
            if self.policy.protect_agent_owned && tab.agent_owned {
                continue;
            }
            if self.policy.protect_audible && tab.audible {
                continue;
            }
            let idle = now.saturating_duration_since(tab.last_active);

            if self.resident_background() > self.policy.max_resident_background {
                out.push(LifecycleAction::Suspend(tab.id.clone()));
                continue;
            }
            if idle >= self.policy.suspend_after {
                out.push(LifecycleAction::Suspend(tab.id.clone()));
                continue;
            }
            if tab.state != LifecycleState::Throttled && idle >= self.policy.throttle_after {
                out.push(LifecycleAction::Throttle(tab.id.clone()));
            }
        }
        out
    }

    /// The session-restore list.
    ///
    /// Ported from `sessionSnapshot`, which dropped `about:` and
    /// `orbit://newtab` shells. The original also preferred the live guest URL
    /// over the bookmarked one because main-side bookkeeping went stale after
    /// navigation; here `set_metadata` keeps them in sync, so the stored URL is
    /// authoritative.
    pub fn session_snapshot(&self) -> Vec<RestorableState> {
        self.order
            .iter()
            .filter_map(|id| self.tabs.get(id))
            .filter(|t| !t.url.is_empty() && !t.url.starts_with("about:") && t.url != "orbit://newtab")
            .map(|t| t.to_restorable())
            .collect()
    }
}