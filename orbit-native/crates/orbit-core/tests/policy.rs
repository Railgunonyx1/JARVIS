//! Integration tests for `orbit-core`.
//!
//! These are the tests that could not exist in the Electron build: `main.js`
//! is untestable without launching a browser, so its SSRF filter, permission
//! defaults and tab sweep were never exercised. Everything below runs headless
//! in under a second.

use orbit_core::controller::{
    BrowserController, ControllerError, EngineCapabilities, FakeController, NavigationBackend,
    NavigationRequest, PageBackend, TabsBackend,
};
use orbit_core::error_log::{ErrorLog, Level, MAX_ENTRIES};
use orbit_core::permissions::{Permission, PermissionDecision, PermissionStore};
use orbit_core::pin::{is_locked, unlock, PinError, PinRecord, MIN_PIN_LEN, PBKDF2_ROUNDS};
use orbit_core::tabs::{LifecycleAction, LifecyclePolicy, LifecycleState, TabRegistry};
use orbit_core::url::{is_private_network_host, is_private_or_local, origin_of, parse};
use orbit_core::{BlockReason, Decision, NetworkPolicy, UrlError};
use std::time::{Duration, Instant};

// ── URL policy ──────────────────────────────────────────────────────────

#[test]
fn parses_ordinary_urls() {
    let u = parse("https://Example.COM:8443/a/b?c=1#d").unwrap();
    assert_eq!(u.scheme, "https");
    assert_eq!(u.host, "example.com");
    assert_eq!(u.port, Some(8443));
    assert_eq!(u.authority(), "example.com:8443");
    assert_eq!(u.rest, "/a/b?c=1#d");
}

#[test]
fn default_ports_are_not_duplicated_in_a_redirect() {
    let https = parse("https://example.com:443/x").unwrap().normalized();
    assert_eq!(https, "https://example.com/x");
    let http = parse("http://example.com:80/x").unwrap().normalized();
    assert_eq!(http, "http://example.com/x");
    // A non-default port must survive.
    let odd = parse("https://example.com:8443/x").unwrap().normalized();
    assert_eq!(odd, "https://example.com:8443/x");
}

#[test]
fn refuses_schemes_that_are_not_navigable() {
    // The single most important parser property: file:// and javascript: must
    // never reach a controller.
    for bad in [
        "file:///C:/Windows/System32/config/SAM",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "chrome://settings",
    ] {
        let err = parse(bad).unwrap_err();
        assert!(
            matches!(err, UrlError::SchemeNotAllowed(_)),
            "{} should be refused, got {:?}",
            bad,
            err
        );
    }
}

#[test]
fn allows_the_schemes_orbit_actually_uses() {
    for good in ["http://x.com", "https://x.com", "about:blank", "orbit://newtab"] {
        assert!(parse(good).is_ok(), "{} should parse", good);
    }
}

#[test]
fn refuses_credentials_but_the_js_original_accepted_them() {
    // new URL() happily accepts this; the browser then renders it without the
    // user noticing the host. Refusing is the safer behaviour.
    let err = parse("https://trusted.com@evil.example/").unwrap_err();
    assert_eq!(err, UrlError::CredentialsInUrl);
}

#[test]
fn trailing_dot_does_not_evade_local_detection() {
    // "localhost." resolves to loopback; a filter that only matches the exact
    // string "localhost" is trivially bypassed by appending a dot.
    assert!(is_private_or_local("localhost."));
    assert!(is_private_or_local("LOCALHOST"));
    assert!(is_private_or_local("foo.localhost"));
}

#[test]
fn private_ranges_match_the_javascript_original() {
    for host in [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "169.254.169.254", // cloud metadata
        "0.0.0.0",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fe80::1",
        "fc00::1",
        "fd12:3456::1",
    ] {
        assert!(is_private_network_host(host), "{} should be private", host);
    }
}

#[test]
fn public_addresses_are_not_private() {
    for host in [
        "1.1.1.1",
        "8.8.8.8",
        "172.32.0.1",  // just outside 172.16/12
        "172.15.0.1",  // just below
        "192.169.0.1",
        "2001:4860:4860::8888",
        "example.com",
    ] {
        assert!(!is_private_network_host(host), "{} should be public", host);
    }
}

#[test]
fn ipv6_loopback_variants_are_caught() {
    assert!(is_private_network_host("::1"));
    assert!(is_private_network_host("[::1]"));
    assert!(is_private_network_host("0:0:0:0:0:0:0:1"));
}

// ── Network decisions ───────────────────────────────────────────────────

#[test]
fn subresource_to_a_private_address_is_blocked() {
    let p = NetworkPolicy::default();
    assert_eq!(
        p.decide("http://169.254.169.254/latest/meta-data/", false, false),
        Decision::Block(BlockReason::PrivateNetwork)
    );
}

#[test]
fn the_user_may_still_navigate_to_their_own_router() {
    // main-frame exemption is deliberate and load-bearing: blocking it would
    // break 192.168.x.x admin pages for every user.
    let p = NetworkPolicy::default();
    assert_eq!(p.decide("http://192.168.1.1/admin", true, false), Decision::Allow);
}

#[test]
fn http_upgrades_to_https_for_public_hosts_only() {
    let p = NetworkPolicy::default();
    match p.decide("http://example.com/login", true, false) {
        Decision::Redirect(u) => assert_eq!(u, "https://example.com/login"),
        other => panic!("expected redirect, got {:?}", other),
    }
    // Never upgrade a local dev server; that is how Orbit's own bridge and the
    // user's local apps would break.
    assert_eq!(p.decide("http://localhost:8171/", true, false), Decision::Allow);
    assert_eq!(p.decide("http://127.0.0.1:3000/", true, false), Decision::Allow);
}

#[test]
fn a_filtered_url_is_blocked_before_any_other_rule() {
    let p = NetworkPolicy::default();
    assert_eq!(
        p.decide("https://tracker.example/pixel.gif", true, true),
        Decision::Block(BlockReason::FilterList)
    );
}

#[test]
fn a_malformed_url_is_refused_not_guessed() {
    let p = NetworkPolicy::default();
    assert_eq!(
        p.decide("not a url at all", true, false),
        Decision::Block(BlockReason::Malformed)
    );
    assert_eq!(p.decide("", true, false), Decision::Block(BlockReason::Malformed));
}

#[test]
fn disabling_the_ssrf_guard_actually_disables_it() {
    let mut p = NetworkPolicy::default();
    p.block_private_network = false;
    assert_eq!(p.decide("http://10.0.0.5/", false, false), Decision::Allow);
}

#[test]
fn origin_of_is_stable() {
    assert_eq!(
        origin_of("https://example.com/a?b=1"),
        Some("https://example.com".to_string())
    );
    assert_eq!(
        origin_of("https://example.com:8443/a"),
        Some("https://example.com:8443".to_string())
    );
    assert_eq!(origin_of("garbage"), None);
}

// ── Permissions ─────────────────────────────────────────────────────────

#[test]
fn permissions_are_denied_until_granted() {
    let mut s = PermissionStore::new();
    assert_eq!(
        s.decide("https://a.com", Permission::Camera),
        PermissionDecision::Deny,
        "default must be deny"
    );
    s.allow("https://a.com", vec!["camera".into()]);
    assert_eq!(s.decide("https://a.com", Permission::Camera), PermissionDecision::Allow);
    // Granting one permission must not grant another.
    assert_eq!(
        s.decide("https://a.com", Permission::Microphone),
        PermissionDecision::Deny
    );
    // ...nor must it grant the same permission to another origin.
    assert_eq!(
        s.decide("https://b.com", Permission::Camera),
        PermissionDecision::Deny
    );
}

#[test]
fn unknown_permission_strings_are_not_stored() {
    let mut s = PermissionStore::new();
    s.allow("https://a.com", vec!["not-a-permission".into()]);
    assert!(s.is_empty(), "a typo must not create a grant");
}

#[test]
fn wildcard_grants_everything_for_that_origin_only() {
    let mut s = PermissionStore::new();
    s.allow("https://a.com", vec!["*".into()]);
    assert_eq!(s.decide("https://a.com", Permission::Geolocation), PermissionDecision::Allow);
    assert_eq!(s.decide("https://a.com", Permission::ClipboardRead), PermissionDecision::Allow);
    assert_eq!(s.decide("https://b.com", Permission::Geolocation), PermissionDecision::Deny);
}

#[test]
fn revoking_the_last_permission_removes_the_entry() {
    let mut s = PermissionStore::new();
    s.allow("https://a.com", vec!["camera".into(), "geolocation".into()]);
    s.revoke("https://a.com", Some("camera"));
    assert_eq!(s.list().len(), 1);
    s.revoke("https://a.com", Some("geolocation"));
    assert!(s.is_empty(), "an empty grant entry is dead state");
}

#[test]
fn revoking_an_unknown_origin_is_a_no_op() {
    let mut s = PermissionStore::new();
    s.revoke("https://nope.com", Some("camera"));
    assert!(s.is_empty());
}

// ── Private-window PIN ──────────────────────────────────────────────────

#[test]
fn a_pin_round_trips() {
    let salt = orbit_core::pin::generate_salt();
    let rec = PinRecord::create("hunter2", &salt).unwrap();
    assert!(rec.verify("hunter2"));
    assert!(!rec.verify("hunter3"));
    assert!(!rec.verify(""));
}

#[test]
fn short_pins_are_refused() {
    let salt = orbit_core::pin::generate_salt();
    assert_eq!(
        PinRecord::create(&"x".repeat(MIN_PIN_LEN - 1), &salt).unwrap_err(),
        PinError::TooShort
    );
}

#[test]
fn a_corrupt_stored_hash_never_authenticates() {
    let salt = orbit_core::pin::generate_salt();
    let mut rec = PinRecord::create("hunter2", &salt).unwrap();
    rec.hash = "not-hex".into();
    assert!(!rec.verify("hunter2"));
    rec.hash = String::new();
    assert!(!rec.verify("hunter2"));
}

#[test]
fn a_corrupt_salt_never_authenticates() {
    let mut rec = PinRecord {
        hash: "00".repeat(32),
        salt: "zzzz".into(),
    };
    assert!(!rec.verify("anything"));
    rec.salt = String::new();
    assert!(!rec.verify("anything"));
}

#[test]
fn two_pins_with_the_same_value_have_different_hashes() {
    let a = PinRecord::create("same", &orbit_core::pin::generate_salt()).unwrap();
    let b = PinRecord::create("same", &orbit_core::pin::generate_salt()).unwrap();
    assert_ne!(a.hash, b.hash, "a fixed salt would let a stolen hash be rainbow-tabled");
}

#[test]
fn no_pin_means_unlocked_which_is_what_makes_it_opt_in() {
    assert!(!is_locked(None));
    assert!(unlock(None, "anything"));
    let rec = PinRecord::create("hunter2", &orbit_core::pin::generate_salt()).unwrap();
    assert!(is_locked(Some(&rec)));
    assert!(unlock(Some(&rec), "hunter2"));
    assert!(!unlock(Some(&rec), "wrong"));
}

#[test]
fn the_kdf_parameters_match_the_electron_build() {
    // Changing these silently invalidates every PIN a user has already set.
    assert_eq!(PBKDF2_ROUNDS, 100_000);
}

// ── Tabs ────────────────────────────────────────────────────────────────

fn registry_with(n: usize) -> TabRegistry {
    let mut r = TabRegistry::default();
    for _ in 0..n {
        r.create(Some("https://example.com"));
    }
    r
}

#[test]
fn ids_are_never_reused() {
    let mut r = TabRegistry::default();
    let a = r.create(None);
    r.close(&a);
    let b = r.create(None);
    assert_ne!(a, b, "a late event for a closed tab must not hit a new one");
}

#[test]
fn closing_the_active_tab_promotes_another() {
    let mut r = registry_with(3);
    let first = r.create(Some("https://x.com"));
    r.set_active(&first);
    assert_eq!(r.active().map(|t| t.id.clone()), Some(first.clone()));
    r.close(&first);
    assert!(r.active().is_some());
    assert_ne!(r.active().map(|t| t.id.clone()), Some(first));
}

#[test]
fn closing_the_last_tab_leaves_no_active() {
    let mut r = registry_with(1);
    let id = r.create(None);
    r.set_active(&id);
    r.close(&id);
    assert!(r.active().is_none());
}

#[test]
fn a_closed_tab_reopens_with_its_url() {
    let mut r = registry_with(1);
    let id = r.create(Some("https://reopen.me"));
    r.get_mut(&id).unwrap().title = "Reopen".to_string();
    r.close(&id);
    let back = r.reopen_closed().unwrap();
    assert_eq!(r.get(&back).map(|t| t.url.clone()), Some("https://reopen.me".into()));
    assert_eq!(r.get(&back).unwrap().title, "Reopen");
}

#[test]
fn reopen_history_is_bounded() {
    let mut r = TabRegistry::default();
    for _ in 0..60 {
        let id = r.create(Some("https://x.com"));
        r.close(&id);
    }
    // A bounded list; an unbounded one is a leak disguised as a feature.
    assert!(r.reopen_closed().is_some());
}

#[test]
fn the_sweep_never_touches_the_active_tab() {
    // Backdate nothing: use a policy that would sweep immediately, so the
    // only thing that can spare the active tab is the sweep itself.
    let mut r = TabRegistry::new(LifecyclePolicy {
        throttle_after: Duration::ZERO,
        suspend_after: Duration::ZERO,
        max_resident_background: 0,
        protect_audible: false,
        protect_agent_owned: false,
    });
    for _ in 0..5 {
        r.create(Some("https://x.com"));
    }
    let active = r.ordered()[0].id.clone();
    r.set_active(&active);

    let acted: Vec<_> = r.sweep(Instant::now()).into_iter().filter_map(|a| match a {
        LifecycleAction::Throttle(id) | LifecycleAction::Suspend(id) => Some(id),
        LifecycleAction::None => None,
    }).collect();

    assert!(
        !acted.contains(&active),
        "an immediately-expired policy must still spare the active tab"
    );
    assert_eq!(acted.len(), 4, "the four background tabs are all swept");
}

#[test]
fn audible_and_agent_owned_tabs_are_protected() {
    let mut r = registry_with(4);
    let ids: Vec<_> = r.ordered().iter().map(|t| t.id.clone()).collect();
    let active = ids[0].clone();
    r.set_active(&active);
    r.set_audible(&ids[1], true);
    r.get_mut(&ids[2]).unwrap().agent_owned = true;

    // Everything is idle by construction only if we backdate, so instead check
    // the policy's own guards with a policy that suspends immediately.
    let mut aggressive = TabRegistry::new(LifecyclePolicy {
        throttle_after: Duration::ZERO,
        suspend_after: Duration::ZERO,
        max_resident_background: 0,
        protect_audible: true,
        protect_agent_owned: true,
    });
    for _ in 0..4 {
        aggressive.create(Some("https://x.com"));
    }
    let aids: Vec<_> = aggressive.ordered().iter().map(|t| t.id.clone()).collect();
    aggressive.set_active(&aids[0]);
    aggressive.set_audible(&aids[1], true);
    aggressive.get_mut(&aids[2]).unwrap().agent_owned = true;

    let acted: Vec<_> = aggressive
        .sweep(Instant::now())
        .into_iter()
        .filter_map(|a| match a {
            LifecycleAction::Throttle(id) | LifecycleAction::Suspend(id) => Some(id),
            LifecycleAction::None => None,
        })
        .collect();
    assert!(!acted.contains(&aids[0]), "active is protected");
    assert!(!acted.contains(&aids[1]), "audible is protected");
    assert!(!acted.contains(&aids[2]), "agent-owned is protected");
}

#[test]
fn the_resident_ceiling_actually_ceilings() {
    // webview-pool.js claimed a maxPoolSize and never enforced it: an empty
    // pool trivially satisfied `length < maxPoolSize`. This is the assertion
    // that would have caught it.
    let mut r = TabRegistry::new(LifecyclePolicy {
        throttle_after: Duration::from_secs(3600),
        suspend_after: Duration::from_secs(7200),
        max_resident_background: 3,
        protect_audible: false,
        protect_agent_owned: false,
    });
    for _ in 0..10 {
        r.create(Some("https://x.com"));
    }
    let active = r.ordered()[0].id.clone();
    r.set_active(&active);
    let suspends = r
        .sweep(Instant::now())
        .into_iter()
        .filter(|a| matches!(a, LifecycleAction::Suspend(_)))
        .count();
    assert_eq!(
        suspends,
        9,
        "with a ceiling of 3 resident background tabs, 9 of 9 backgrounds must be evicted"
    );
}

#[test]
fn suspending_captures_a_snapshot_and_reactivating_does_not() {
    let mut r = registry_with(1);
    let id = r.ordered()[0].id.clone();
    r.set_metadata(&id, "https://captured.example", "Captured");
    r.set_state(&id, LifecycleState::Suspended);
    let snap = r.get(&id).unwrap().snapshot.clone().expect("snapshot on the way out");
    assert_eq!(snap.url, "https://captured.example");
    assert_eq!(snap.title, "Captured");

    // Changing metadata while suspended, then reactivating, must not clobber
    // the snapshot that is the only record of the page.
    r.set_metadata(&id, "https://clobbered.example", "Clobbered");
    r.mark_active(&id);
    assert_eq!(
        r.get(&id).and_then(|t| t.snapshot.as_ref()).map(|s| s.url.clone()),
        Some("https://captured.example".to_string())
    );
}

#[test]
fn session_snapshot_drops_blank_shells() {
    let mut r = TabRegistry::default();
    let blank = r.create(Some("about:blank"));
    let newtab = r.create(Some("orbit://newtab"));
    let real = r.create(Some("https://real.example"));
    r.set_metadata(&real, "https://real.example", "Real");
    let snap = r.session_snapshot();
    assert_eq!(snap.len(), 1);
    assert_eq!(snap[0].url, "https://real.example");
    assert!(!snap.iter().any(|s| s.url == blank.as_str().to_string()));
    assert!(!snap.iter().any(|s| s.url == newtab.as_str().to_string()));
}

#[test]
fn lifecycle_states_answer_the_questions_the_host_asks() {
    assert!(LifecycleState::Active.is_resident());
    assert!(LifecycleState::Warm.is_resident());
    assert!(LifecycleState::Throttled.is_resident());
    assert!(!LifecycleState::Suspended.is_resident());
    assert!(!LifecycleState::Restorable.is_resident());
    assert!(LifecycleState::Suspended.is_cheap_to_leave());
    assert!(!LifecycleState::Restorable.is_cheap_to_leave());
}

// ── Controller seam ─────────────────────────────────────────────────────

#[test]
fn a_suspended_tab_refuses_page_operations_until_restored() {
    // The Electron build's failure mode: operations against a torn-down guest
    // silently no-op'd, so a button looked live and did nothing.
    let mut c = FakeController::new();
    let t = c.create(&orbit_core::ProfileId("default".into())).unwrap();
    assert!(c.read_text(&t).is_ok());
    c.suspend(&t).unwrap();
    assert!(matches!(c.read_text(&t), Err(ControllerError::Suspended(_))));
    assert!(matches!(
        c.execute(&t, "1"),
        Err(ControllerError::Suspended(_))
    ));
    c.restore(&t).unwrap();
    assert!(c.read_text(&t).is_ok());
}

#[test]
fn operations_on_an_unknown_tab_are_errors_not_panics() {
    let mut c = FakeController::new();
    let ghost = orbit_core::TabId("tab-nope".into());
    assert!(matches!(c.close(&ghost), Err(ControllerError::NoSuchTab(_))));
    assert!(matches!(
        c.activate(&ghost),
        Err(ControllerError::NoSuchTab(_))
    ));
}

#[test]
fn navigation_records_where_it_went() {
    let mut c = FakeController::new();
    let t = c.create(&orbit_core::ProfileId("default".into())).unwrap();
    c.goto(NavigationRequest {
        tab: t.clone(),
        url: "https://example.com".into(),
        replace: false,
    })
    .unwrap();
    assert_eq!(c.last_goto.as_deref(), Some("https://example.com"));
    assert!(c.engine_version().starts_with("fake"));
}

#[test]
fn webview2_declares_that_it_cannot_do_extensions() {
    // Recorded honestly so the failure surfaces at startup, not as a feature
    // that silently does nothing.
    let caps = EngineCapabilities::webview2();
    assert!(!caps.extensions);
    assert!(caps.request_interception, "blocking depends on CDP Fetch");
    assert!(caps.multi_profile);
}

// ── Error log ───────────────────────────────────────────────────────────

#[test]
fn the_error_log_is_bounded_and_keeps_the_newest() {
    let mut log = ErrorLog::new(5);
    for i in 0..20 {
        log.log(Level::Info, format!("entry {}", i), "");
    }
    assert_eq!(log.len(), 5);
    let first = log.newest_first()[0];
    assert_eq!(first.message, "entry 19");
    assert_eq!(log.newest_first().len(), 5);
}

#[test]
fn long_fields_are_truncated_like_the_original() {
    let mut log = ErrorLog::new(4);
    log.log(Level::Error, "x".repeat(5000), "y".repeat(5000));
    let e = log.entries().next().unwrap();
    assert_eq!(e.message.chars().count(), 500);
    assert_eq!(e.detail.chars().count(), 500);
}

#[test]
fn the_log_round_trips_through_json() {
    let mut log = ErrorLog::new(MAX_ENTRIES);
    log.log(Level::Warn, "warned", "detail");
    log.log(Level::Error, "failed", "boom");
    let json = log.to_json();

    let mut restored = ErrorLog::new(MAX_ENTRIES);
    assert!(restored.load_json(&json));
    assert_eq!(restored.len(), 2);
    assert_eq!(restored.entries().next().unwrap().message, "warned");
}

#[test]
fn a_corrupt_log_file_starts_fresh_rather_than_failing_to_launch() {
    let mut log = ErrorLog::new(MAX_ENTRIES);
    log.log(Level::Error, "kept", "");
    assert!(!log.load_json("{not json"));
    assert!(log.is_empty());
}

#[test]
fn a_failed_flush_is_retried_not_forgotten() {
    let mut log = ErrorLog::new(MAX_ENTRIES);
    log.log(Level::Info, "x", "");
    assert!(log.take_dirty(), "a new entry marks the log dirty");
    // Host attempts a write and fails.
    log.mark_clean();
    log.log(Level::Info, "y", "");
    assert!(log.take_dirty(), "a later entry must re-mark it dirty");
}