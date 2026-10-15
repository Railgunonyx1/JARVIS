//! URL governance.
//!
//! Ported line-for-line from `orbit-browser/main.js` (`isPrivateOrLocalHost`,
//! `isPrivateNetworkHost`, `urlFor`, `siteOriginOf`) and `security.js`
//! (`shouldBlock`, `upgradeToHttps`). The point of porting them is not the
//! language: it is that this file has no `window`, no I/O and no Electron, so
//! every branch below is reachable from `cargo test` on a headless machine.
//!
//! Behaviour-preserving note: the JavaScript original silently returns `null`
//! from `new URL(...)` for unparseable input and callers treat that as "not a
//! problem". Here, an unparseable URL is an explicit error rather than a
//! default-deny, because guessing is how SSRF filters get bypassed.

use std::net::Ipv4Addr;

/// Schemes Orbit is willing to navigate to. Anything else is refused before
/// it reaches a browser controller.
pub const ALLOWED_SCHEMES: [&str; 4] = ["http", "https", "about", "orbit"];

/// A minimal URL shape. Orbit deliberately does not pull a URL crate: the
/// browser hands us strings, and the only fields policy needs are the scheme
/// and the host.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedUrl {
    pub scheme: String,
    pub host: String,
    pub port: Option<u16>,
    /// Everything after `scheme://host[:port]`.
    pub rest: String,
}

impl ParsedUrl {
    /// `host:port` if an explicit non-default port is present, else `host`.
    pub fn authority(&self) -> String {
        match self.port {
            Some(p) => format!("{}:{}", self.host, p),
            None => self.host.clone(),
        }
    }

    /// `scheme://authority + rest`, minus the default port.
    pub fn normalized(&self) -> String {
        let default_port = match self.scheme.as_str() {
            "http" => Some(80),
            "https" => Some(443),
            _ => None,
        };
        let port = match self.port {
            Some(p) if Some(p) != default_port => format!(":{}", p),
            _ => String::new(),
        };
        format!("{}://{}{}{}", self.scheme, self.host, port, self.rest)
    }
}

/// Parse just enough of a URL to apply policy.
///
/// Deliberately stricter than the JS `new URL()`, which accepts many shapes a
/// browser will then reinterpret. Returns `Err` rather than guessing, because
/// the failure mode of guessing here is a security bypass.
pub fn parse(url: &str) -> Result<ParsedUrl, UrlError> {
    let url = url.trim();
    if url.is_empty() {
        return Err(UrlError::Empty);
    }

    let (scheme, rest) = url.split_once(':').ok_or(UrlError::NoScheme)?;
    let scheme = scheme.to_ascii_lowercase();
    if !ALLOWED_SCHEMES.contains(&scheme.as_str()) {
        return Err(UrlError::SchemeNotAllowed(scheme));
    }

    // about: and orbit: are opaque to us; their host is everything after the
    // colon and there is no authority to split.
    if scheme == "about" || scheme == "orbit" {
        return Ok(ParsedUrl {
            scheme,
            host: rest.trim_start_matches("//").to_ascii_lowercase(),
            port: None,
            rest: String::new(),
        });
    }

    let after = rest
        .strip_prefix("//")
        .ok_or(UrlError::MalformedAuthority)?;
    let (authority, path) = match after.find(['/', '?', '#']) {
        Some(i) => (&after[..i], &after[i..]),
        None => (after, ""),
    };
    if authority.is_empty() {
        return Err(UrlError::MalformedAuthority);
    }

    // Credentials in an authority are a phishing vector and nothing in Orbit
    // needs them; refuse rather than strip, so the caller cannot proceed on a
    // URL the user cannot see.
    if authority.contains('@') {
        return Err(UrlError::CredentialsInUrl);
    }

    let (host, port) = split_host_port(authority)?;
    if host.is_empty() {
        return Err(UrlError::MalformedAuthority);
    }

    Ok(ParsedUrl {
        scheme,
        host,
        port,
        rest: path.to_string(),
    })
}

fn split_host_port(authority: &str) -> Result<(String, Option<u16>), UrlError> {
    if let Some(stripped) = authority.strip_prefix('[') {
        // IPv6 literal: [::1] or [::1]:8080
        let close = stripped
            .find(']')
            .ok_or(UrlError::MalformedAuthority)?;
        let host = format!("[{}]", &stripped[..close]);
        let after = &stripped[close + 1..];
        if after.is_empty() {
            return Ok((host, None));
        }
        let port = after
            .strip_prefix(':')
            .ok_or(UrlError::MalformedAuthority)?
            .parse()
            .map_err(|_| UrlError::BadPort)?;
        return Ok((host, Some(port)));
    }

    match authority.rsplit_once(':') {
        Some((h, p)) => {
            // A bare IPv6 without brackets would have split on its colons; a
            // non-numeric tail means it was never a port.
            let port = p.parse().map_err(|_| UrlError::BadPort)?;
            Ok((h.to_ascii_lowercase(), Some(port)))
        }
        None => Ok((authority.to_ascii_lowercase(), None)),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UrlError {
    Empty,
    NoScheme,
    SchemeNotAllowed(String),
    MalformedAuthority,
    CredentialsInUrl,
    BadPort,
}

impl std::fmt::Display for UrlError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            UrlError::Empty => write!(f, "url is empty"),
            UrlError::NoScheme => write!(f, "url has no scheme"),
            UrlError::SchemeNotAllowed(s) => write!(f, "scheme not allowed: {}", s),
            UrlError::MalformedAuthority => write!(f, "url has a malformed authority"),
            UrlError::CredentialsInUrl => write!(f, "url must not embed credentials"),
            UrlError::BadPort => write!(f, "url has a non-numeric port"),
        }
    }
}

impl std::error::Error for UrlError {}

/// Strip a single trailing dot, lowercase, and remove IPv6 brackets.
///
/// The JavaScript original did `replace(/\.$/, "")` inline in several places;
/// doing it once here removes three chances to forget it.
fn canonical_host(host: &str) -> String {
    host.trim()
        .trim_start_matches('[')
        .trim_end_matches(']')
        .trim_end_matches('.')
        .to_ascii_lowercase()
}

/// `localhost`, `*.local`, `*.localhost`, and any loopback / private / CGNAT
/// / link-local address.
///
/// Ported from `isPrivateOrLocalHost`.
pub fn is_private_or_local(host: &str) -> bool {
    let h = canonical_host(host);
    if h.is_empty() {
        return false;
    }
    if h == "localhost" || h.ends_with(".local") || h.ends_with(".localhost") {
        return true;
    }

    // An IPv6 loopback reaches us as "::1" (or "::" / "0:0:0:0:0:0:0:1" after
    // canonicalisation elsewhere); match the shape rather than every spelling.
    if let Some(v6) = parse_ipv6(&h) {
        return is_private_v6(&v6);
    }

    if let Ok(v4) = h.parse::<Ipv4Addr>() {
        return is_private_v4(v4);
    }
    false
}

fn is_private_v4(ip: Ipv4Addr) -> bool {
    let o = ip.octets();
    match o[0] {
        127 => true,                                    // loopback
        10 => true,                                     // RFC1918
        192 if o[1] == 168 => true,                     // RFC1918
        172 if (16..=31).contains(&o[1]) => true,        // RFC1918
        169 if o[1] == 254 => true,                      // link-local
        0 => true,                                      // "this network"
        _ if o[0] >= 224 => true,                        // multicast + reserved
        _ => false,
    }
}

fn parse_ipv6(h: &str) -> Option<std::net::Ipv6Addr> {
    // Reject anything with a zone id or a port left over; those are not hosts.
    if h.contains('%') {
        return None;
    }
    h.parse().ok()
}

fn is_private_v6(ip: &std::net::Ipv6Addr) -> bool {
    if ip.is_loopback() || ip.is_unspecified() {
        return true;
    }
    let seg = ip.segments();
    match seg[0] {
        // fe80::/10 link-local
        0xfe80..=0xfebf => true,
        // fc00::/7 unique local
        0xfc00..=0xfdff => true,
        // IPv4-mapped (::ffff:a.b.c.d) inherits the v4 verdict.
        0 | 0xffff => ip.to_ipv4().map(|v| is_private_v4(v)).unwrap_or(false),
        _ => false,
    }
}

/// Private, loopback, link-local, CGNAT or otherwise non-routable.
///
/// Ported from `isPrivateNetworkHost`, which additionally covered the IPv6
/// ranges and multicast.
pub fn is_private_network_host(host: &str) -> bool {
    let h = canonical_host(host);
    if h.is_empty() {
        return false;
    }
    if is_private_or_local(&h) {
        return true;
    }
    if let Some(v6) = parse_ipv6(&h) {
        return is_private_v6(&v6);
    }
    // ff00::/8 multicast.
    if let Some(v6) = parse_ipv6(&h) {
        if v6.segments()[0] == 0xff00 {
            return true;
        }
    }
    false
}

/// Origin (`scheme://host:port`) for permission decisions, or `None` if the URL
/// does not parse. Ported from `siteOriginOf`.
pub fn origin_of(url: &str) -> Option<String> {
    let p = parse(url).ok()?;
    if p.scheme == "about" || p.scheme == "orbit" {
        return Some(format!("{}://{}", p.scheme, p.host));
    }
    Some(format!("{}://{}", p.scheme, p.authority()))
}

/// What Orbit decided to do with a navigation or subresource request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Decision {
    Allow,
    /// Cancel the request entirely (blocked tracker, SSRF, private-network).
    Block(BlockReason),
    /// Issue this URL instead (HTTPS upgrade).
    Redirect(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BlockReason {
    /// Matched the ad/tracker filter list.
    FilterList,
    /// A subresource pointed at a private/loopback address.
    PrivateNetwork,
    /// The scheme is not one Orbit navigates to.
    SchemeNotAllowed,
    /// Unparseable — refused rather than guessed.
    Malformed,
}

#[derive(Debug, Clone)]
pub struct NetworkPolicy {
    /// Cancel subresources aimed at private/loopback addresses (SSRF guard).
    pub block_private_network: bool,
    /// Rewrite `http://` to `https://` for non-local hosts.
    pub https_upgrade: bool,
    pub block_third_party_cookies: bool,
}

impl Default for NetworkPolicy {
    fn default() -> Self {
        Self {
            block_private_network: true,
            https_upgrade: true,
            block_third_party_cookies: false,
        }
    }
}

impl NetworkPolicy {
    /// Decide what to do with a request.
    ///
    /// `resource_type` is `true` for the main frame and `false` for
    /// subresources, mirroring the JS `details.resourceType !== "mainFrame"`
    /// check. The SSRF guard deliberately does **not** apply to the main
    /// frame: a user typing `http://192.168.1.1` to reach their own router is
    /// legitimate, but a page silently probing it is not.
    pub fn decide(&self, url: &str, is_main_frame: bool, is_filtered: bool) -> Decision {
        if is_filtered {
            return Decision::Block(BlockReason::FilterList);
        }

        let parsed = match parse(url) {
            Ok(p) => p,
            Err(UrlError::SchemeNotAllowed(_)) => {
                return Decision::Block(BlockReason::SchemeNotAllowed)
            }
            Err(_) => return Decision::Block(BlockReason::Malformed),
        };

        if self.block_private_network && !is_main_frame && is_private_network_host(&parsed.host) {
            return Decision::Block(BlockReason::PrivateNetwork);
        }

        if self.https_upgrade
            && parsed.scheme == "http"
            && !is_private_or_local(&parsed.host)
        {
            let upgraded = ParsedUrl {
                scheme: "https".into(),
                ..parsed
            };
            return Decision::Redirect(upgraded.normalized());
        }

        Decision::Allow
    }
}