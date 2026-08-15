/**
 * Resolves theme CSS custom properties to concrete color strings so <canvas>
 * (which can't read `var(--x)`) can paint with the exact console palette.
 * Values are cached and reused; the palette is static after boot.
 */
const cache = new Map<string, string>()

export function token(name: string): string {
  if (typeof window === "undefined") return "#888"
  if (cache.has(name)) return cache.get(name) as string
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const val = raw || "#888"
  cache.set(name, val)
  return val
}

export const palette = {
  get accent() {
    return token("--accent")
  },
  get info() {
    return token("--info")
  },
  get online() {
    return token("--online")
  },
  get warn() {
    return token("--warn")
  },
  get error() {
    return token("--error")
  },
  get muted() {
    return token("--muted-foreground")
  },
  get border() {
    return token("--border-strong")
  },
}
