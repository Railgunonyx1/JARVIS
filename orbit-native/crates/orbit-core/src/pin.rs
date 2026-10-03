//! Private-window PIN.
//!
//! Ported from `main.js` (`hashPin`, `setPrivatePin`, `verifyPrivatePin`,
//! `clearPrivatePin`). The KDF parameters are unchanged — PBKDF2-HMAC-SHA256,
//! 100_000 iterations, 16-byte salt — so an existing PIN keeps working.
//!
//! One deliberate behaviour change: the JavaScript compared hex digests with
//! `===`, which returns as soon as two characters differ and is a timing
//! side-channel on a secret. This uses a constant-time comparison.

use subtle::ConstantTimeEq;

/// PBKDF2 iteration count. Matches the Electron build; changing it silently
/// invalidates every stored PIN, so it is a versioned constant.
pub const PBKDF2_ROUNDS: u32 = 100_000;
const SALT_BYTES: usize = 16;
const KEY_BYTES: usize = 32;

/// Minimum PIN length, matching the JavaScript guard.
pub const MIN_PIN_LEN: usize = 4;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PinError {
    TooShort,
    /// Salt must be exactly `SALT_BYTES` hex-encoded bytes.
    BadSalt,
    /// The KDF itself refused. Propagated rather than ignored: a dropped
    /// error here would leave `key` as all-zeroes and turn every PIN into a
    /// constant.
    KdfFailed,
}

impl std::fmt::Display for PinError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PinError::TooShort => write!(f, "PIN must be at least {} characters", MIN_PIN_LEN),
            PinError::BadSalt => write!(f, "stored PIN salt is malformed"),
            PinError::KdfFailed => write!(f, "key derivation failed"),
        }
    }
}

impl std::error::Error for PinError {}

/// Stored material. `hash` is hex; `salt` is hex.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PinRecord {
    pub hash: String,
    pub salt: String,
}

impl PinRecord {
    pub fn derive(pin: &str, salt_hex: &str) -> Result<Self, PinError> {
        let salt = decode_salt(salt_hex)?;
        let mut key = [0u8; KEY_BYTES];
        pbkdf2::pbkdf2::<hmac::Hmac<sha2::Sha256>>(pin.as_bytes(), &salt, PBKDF2_ROUNDS, &mut key)
            .map_err(|_| PinError::KdfFailed)?;
        Ok(Self {
            hash: hex::encode(key),
            salt: salt_hex.to_string(),
        })
    }

    /// Create a fresh record. The salt must come from a CSPRNG; passing
    /// `generate_salt` is the only supported way to make one.
    pub fn create(pin: &str, salt_hex: &str) -> Result<Self, PinError> {
        if pin.chars().count() < MIN_PIN_LEN {
            return Err(PinError::TooShort);
        }
        Self::derive(pin, salt_hex)
    }

    /// Verify a candidate. No record means "no PIN configured", which the
    /// Electron build treated as allow — kept, because that is what makes the
    /// feature opt-in.
    pub fn verify(&self, pin: &str) -> bool {
        let Ok(expected) = decode_salt(&self.salt) else {
            return false;
        };
        let mut key = [0u8; KEY_BYTES];
        if pbkdf2::pbkdf2::<hmac::Hmac<sha2::Sha256>>(
            pin.as_bytes(),
            &expected,
            PBKDF2_ROUNDS,
            &mut key,
        )
        .is_err()
        {
            return false;
        }
        let stored = match hex::decode(&self.hash) {
            Ok(b) if b.len() == KEY_BYTES => b,
            // A malformed stored hash must never authenticate.
            _ => return false,
        };
        stored.ct_eq(&key).into()
    }
}

fn decode_salt(salt_hex: &str) -> Result<Vec<u8>, PinError> {
    let bytes = hex::decode(salt_hex).map_err(|_| PinError::BadSalt)?;
    if bytes.len() != SALT_BYTES {
        return Err(PinError::BadSalt);
    }
    Ok(bytes)
}

/// Whether any PIN is configured.
pub fn is_locked(record: Option<&PinRecord>) -> bool {
    record.is_some()
}

/// The Electron build's `verifyPrivatePin`: no record means unlocked.
pub fn unlock(record: Option<&PinRecord>, pin: &str) -> bool {
    match record {
        None => true,
        Some(r) => r.verify(pin),
    }
}

/// Salt for a new PIN, from the OS CSPRNG.
///
/// Failures panic rather than falling back: a predictable salt silently
/// downgrades PBKDF2 from 100k rounds to a dictionary attack, and a PIN gate
/// that looks secure but is not is worse than one that visibly fails.
pub fn generate_salt() -> String {
    let mut buf = [0u8; SALT_BYTES];
    getrandom::getrandom(&mut buf).expect("OS CSPRNG unavailable; refusing to generate a weak PIN salt");
    hex::encode(buf)
}