export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8765'

let _token = ''

export function setAuthToken(t) { _token = t }

export function getAuthToken() { return _token }

export function authHeaders() {
  const h = { 'Content-Type': 'application/json' }
  if (_token) h['Authorization'] = 'Bearer ' + _token
  return h
}

export async function fetchAuthToken() {
  try {
    const r = await fetch(`${API_BASE}/api/auth/token`)
    const d = await r.json()
    if (d.ok && d.token) setAuthToken(d.token)
  } catch { /* ignore */ }
}

export async function checkHealth() {
  const r = await fetch(`${API_BASE}/api/health`)
  return r.json()
}

export async function fetchStatus() {
  const r = await fetch(`${API_BASE}/api/status`)
  return r.json()
}
