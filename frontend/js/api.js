// API client: same-origin by default (Netlify proxies /api), or cross-origin with credentials when config.js sets VERITY_API_BASE.
// CSRF token is kept in memory only (never localStorage); the session itself lives in an HttpOnly cookie the page cannot read.
const BASE = (window.VERITY_API_BASE || "").replace(/\/$/, "");
let csrf = "";
export const setCsrf = (t) => { csrf = t || ""; };
export class ApiError extends Error {
  constructor(status, code, message, extra = {}) { super(message); this.status = status; this.code = code; this.fields = extra.fields || {}; this.extra = extra; }
}
async function once(path, { method = "GET", body, headers = {}, timeout = 15000, signal } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  if (signal) signal.addEventListener("abort", () => ctl.abort());
  const h = { Accept: "application/json", ...headers };
  if (body !== undefined) h["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) h["X-CSRF-Token"] = csrf;
  let res;
  try {
    res = await fetch(BASE + path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body), signal: ctl.signal, credentials: BASE ? "include" : "same-origin" });
  } catch (e) {
    if (signal && signal.aborted) throw e;
    throw new ApiError(0, ctl.signal.aborted ? "timeout" : "network", ctl.signal.aborted ? "The server took too long to respond. Please try again." : "Can't reach the Verity server. Check your connection and try again.");
  } finally { clearTimeout(timer); }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) {
    const e = (data && data.error) || {};
    throw new ApiError(res.status, e.code || "error", e.message || (res.status >= 500 ? "Something went wrong on our side. Please try again." : "Request failed."), e);
  }
  return data;
}
export async function api(path, opts = {}) {
  try { return await once(path, opts); }
  catch (e) {
    if (e instanceof ApiError && e.code === "csrf" && !opts._retried) {      // session rotated or expired: refresh the token once
      const me = await once("/api/auth/me");
      setCsrf(me.csrf);
      return api(path, { ...opts, _retried: true });
    }
    throw e;
  }
}
export const get = (p, o) => api(p, o);
export const post = (p, body = {}, o = {}) => api(p, { method: "POST", body, ...o });
export const put = (p, body = {}, o = {}) => api(p, { method: "PUT", body, ...o });
export const patch = (p, body = {}, o = {}) => api(p, { method: "PATCH", body, ...o });
export const del = (p, body, o = {}) => api(p, { method: "DELETE", body, ...o });
export const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/[^A-Za-z0-9_-]/g, "");
