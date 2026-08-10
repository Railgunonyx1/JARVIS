/** Bounded exponential backoff with jitter (mirrors daemon/client.py). */

export interface BackoffOptions {
  maxAttempts?: number
  baseDelayMs?: number
  maxDelayMs?: number
}

export function backoffDelayMs(attempt: number, opts: BackoffOptions = {}): number {
  const base = opts.baseDelayMs ?? 250
  const ceiling = opts.maxDelayMs ?? 5000
  const exponent = Math.min(ceiling, base * 2 ** (attempt - 1))
  return Math.round(exponent * (0.5 + Math.random() * 0.5))
}

export class Backoff {
  readonly maxAttempts: number
  private readonly baseDelayMs: number
  private readonly maxDelayMs: number
  private attempt = 0

  constructor(opts: BackoffOptions = {}) {
    this.maxAttempts = opts.maxAttempts ?? 5
    this.baseDelayMs = opts.baseDelayMs ?? 250
    this.maxDelayMs = opts.maxDelayMs ?? 5000
  }

  next(): number | null {
    this.attempt += 1
    if (this.attempt > this.maxAttempts) {
      return null
    }
    return backoffDelayMs(this.attempt, {
      baseDelayMs: this.baseDelayMs,
      maxDelayMs: this.maxDelayMs,
    })
  }

  reset(): void {
    this.attempt = 0
  }
}
