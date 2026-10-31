use std::future::Future;
/// Core runtime helpers.

use std::time::Duration;
use tokio::time::Instant;

/// A simple deadline helper used for startup and keepalive-style timeouts.
pub fn timeout<F, T>(dur: Duration, f: F) -> impl Future<Output = Option<T>>
where
    F: std::future::Future<Output = T>,
{
    let _start = Instant::now();
    async move {
        tokio::select! {
            result = f => {
                Some(result)
            }
            _ = tokio::time::sleep(dur) => {
                None
            }
        }
    }
}
