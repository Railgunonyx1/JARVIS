let _token = "";

export function setAuthToken(t) { _token = t; }
export function getAuthToken() { return _token; }

export function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (_token) h["Authorization"] = "Bearer " + _token;
  return h;
}
