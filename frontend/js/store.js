// Client state. Anything sensitive stays server-side; the only things persisted in the browser are non-sensitive product IDs
// (compare tray in sessionStorage, guest "recently viewed" in localStorage). No tokens, no personal data.
import { get, post, del, setCsrf, ApiError } from "./api.js";

export const state = { user: null, meta: null, cart: { items_count: 0 }, wishlist: new Set(), compare: [], offline: false };
const bus = new EventTarget();
export const on = (n, fn) => { bus.addEventListener(n, fn); return () => bus.removeEventListener(n, fn); };
export const emit = (n, detail) => bus.dispatchEvent(new CustomEvent(n, { detail }));
const safe = (fn, d) => { try { return fn(); } catch { return d; } };

state.compare = safe(() => JSON.parse(sessionStorage.getItem("verity.compare") || "[]"), []).filter((x) => typeof x === "string").slice(0, 4);

const LOCAL_WISH = "verity.wish";                // guests keep a wishlist on this device: product IDs only, nothing personal
export const guestWish = () => new Set(safe(() => JSON.parse(localStorage.getItem(LOCAL_WISH) || "[]"), []).filter((x) => typeof x === "string").slice(0, 100));
const saveGuestWish = () => safe(() => localStorage.setItem(LOCAL_WISH, JSON.stringify([...state.wishlist])));
export async function mergeGuestWishlist(ids) {   // after sign-in: move this device's saved items into the account
  for (const id of ids) { try { await post("/api/account/wishlist", { product_id: id }); state.wishlist.add(id); } catch { /* product may no longer exist */ } }
  safe(() => localStorage.removeItem(LOCAL_WISH)); emit("wishlist", null);
}
export function applySession(s) {
  setCsrf(s.csrf);
  state.user = s.user || null;
  state.wishlist = s.user ? new Set(s.wishlist_ids || []) : guestWish();
  emit("session", state.user);
}
export async function boot() {
  const [me, meta] = await Promise.allSettled([get("/api/auth/me"), get("/api/meta")]);
  if (me.status === "fulfilled") applySession(me.value); else state.offline = true;
  if (meta.status === "fulfilled") state.meta = meta.value; else state.offline = true;
  refreshCart();
}
export async function refreshCart() {
  try { setCart(await get("/api/cart")); } catch { /* header badge simply stays as it was */ }
}
export function setCart(c) { state.cart = c; emit("cart", c); }
export const isAdmin = () => state.user && state.user.role === "admin";

export function inCompare(id) { return state.compare.includes(id); }
export function toggleCompare(id) {
  const i = state.compare.indexOf(id);
  if (i >= 0) state.compare.splice(i, 1);
  else { if (state.compare.length >= (state.meta?.max_compare || 4)) return false; state.compare.push(id); }
  sessionStorage.setItem("verity.compare", JSON.stringify(state.compare));
  emit("compare", state.compare);
  return true;
}
export function setCompare(ids) { state.compare = ids.slice(0, 4); sessionStorage.setItem("verity.compare", JSON.stringify(state.compare)); emit("compare", state.compare); }

export async function toggleWish(id) {
  if (!state.user) {                                // guest: local list, no account needed
    state.wishlist.has(id) ? state.wishlist.delete(id) : state.wishlist.add(id);
    saveGuestWish(); emit("wishlist", id);
    return state.wishlist.has(id);
  }
  if (state.wishlist.has(id)) { await del(`/api/account/wishlist/${encodeURIComponent(id)}`); state.wishlist.delete(id); }
  else { await post("/api/account/wishlist", { product_id: id }); state.wishlist.add(id); }
  emit("wishlist", id);
  return state.wishlist.has(id);
}
export async function trackView(id) {
  if (state.user) { try { await post("/api/account/recent", { product_id: id }); } catch { /* non-critical */ } return; }
  const list = [id, ...safe(() => JSON.parse(localStorage.getItem("verity.recent") || "[]"), []).filter((x) => x !== id)].slice(0, 12);
  safe(() => localStorage.setItem("verity.recent", JSON.stringify(list)));
}
export const guestRecent = () => safe(() => JSON.parse(localStorage.getItem("verity.recent") || "[]"), []);
export const clearGuestRecent = () => safe(() => localStorage.removeItem("verity.recent"));
