// Hash router with guards, lazy-loaded views, focus management and in-place updates for views that support it.
import { state, isAdmin } from "./store.js";
import { h, mount, icon } from "./dom.js";

const ROUTES = [
  [/^\/?$/, "home", () => import("./views/home.js")],
  [/^\/shop$/, "shop", () => import("./views/shop.js")],
  [/^\/product\/([^/]+)$/, "product", () => import("./views/product.js"), ["id"]],
  [/^\/cart$/, "cart", () => import("./views/cart.js")],
  [/^\/wishlist$/, "wishlist", () => import("./views/wishlist.js")],
  [/^\/(login|register|forgot|reset)$/, "auth", () => import("./views/auth.js"), ["mode"]],
  [/^\/account(?:\/([^/]+))?(?:\/([^/]+))?$/, "account", () => import("./views/account.js"), ["tab", "sub"], "auth"],
  [/^\/compare$/, "compare", () => import("./views/compare.js")],
  [/^\/smartmatch$/, "smartmatch", () => import("./views/smartmatch.js")],
  [/^\/basket$/, "basket", () => import("./views/basket.js")],
  [/^\/admin(?:\/([^/]+))?$/, "admin", () => import("./views/admin.js"), ["tab"], "admin"],
  [/^\/(about|privacy|policies)$/, "info", () => import("./views/info.js"), ["page"]],
];
const main = () => document.getElementById("main");
let current = null, token = 0;

export function parse(hash = location.hash) {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { path: path.startsWith("/") ? path : "/" + path, query: new URLSearchParams(query) };
}
export const navigate = (to, { replace = false } = {}) => {
  const target = to.startsWith("#") ? to : "#" + to;
  if (replace) { history.replaceState(null, "", target); window.dispatchEvent(new HashChangeEvent("hashchange")); } else location.hash = target;
};
export const setQuery = (obj) => {            // update the URL's query without leaving the view
  const { path, query } = parse();
  for (const [k, v] of Object.entries(obj)) (v === "" || v == null || v === false) ? query.delete(k) : query.set(k, v);
  const s = query.toString();
  navigate(path + (s ? "?" + s : ""), { replace: true });
};
export const loginUrl = (next) => `/login?next=${encodeURIComponent(next || parse().path + (location.hash.includes("?") ? "?" + location.hash.split("?")[1] : ""))}`;

function skeleton() {
  return h("div", { class: "wrap section", "aria-busy": "true" }, h("div", { class: "sk", style: { height: "44px", width: "min(420px,70%)" } }),
    h("div", { class: "grid", style: { "margin-top": "28px" } }, ...Array.from({ length: 4 }, () => h("div", { class: "sk sk-card" }))));
}
function failure(err, retry) {
  return h("div", { class: "wrap section" }, h("div", { class: "state err", role: "alert" }, icon("alert"), h("h2", null, "We couldn't load this page"),
    h("p", null, err.message || "Something went wrong."), h("button", { class: "btn", onclick: retry }, "Try again")));
}
export async function render() {
  const { path, query } = parse();
  const my = ++token;
  let match = null;
  for (const [rx, key, loader, names = [], guard] of ROUTES) {
    const m = rx.exec(path);
    if (m) { match = { key, loader, guard, params: Object.fromEntries(names.map((n, i) => [n, m[i + 1] ? decodeURIComponent(m[i + 1]) : ""])) }; break; }
  }
  const el = main();
  if (!match) match = { key: "notfound", loader: () => import("./views/info.js"), params: { page: "notfound" } };
  if (match.guard === "auth" && !state.user) return navigate(loginUrl(), { replace: true });
  if (match.guard === "admin" && !state.user) return navigate(loginUrl(), { replace: true });
  const ctx = { ...match.params, query, path, navigate, setQuery, title: null };
  if (match.guard === "admin" && !isAdmin()) { mount(el, h("div", { class: "wrap section" }, h("div", { class: "state", role: "alert" }, icon("lock"), h("h2", null, "Administrators only"), h("p", null, "This area needs an administrator account. The server checks this on every request."), h("a", { class: "btn", href: "#/" }, "Back to the shop")))); document.title = "Not allowed · Verity"; return; }
  if (current && current.key === match.key && current.inst && current.inst.update) { try { await current.inst.update(ctx); return; } catch (e) { /* fall through to a full render */ } }
  if (current && current.inst && current.inst.destroy) { try { current.inst.destroy(); } catch { /* ignore */ } }
  current = null;
  mount(el, skeleton());
  try {
    const mod = await match.loader();
    const inst = await mod.default(ctx);
    if (my !== token) return;
    const node = inst.node || inst;
    mount(el, h("div", { class: "view" }, node));
    current = { key: match.key, inst: inst.node ? inst : null };
    document.title = (ctx.title ? ctx.title + " · " : "") + "Verity";
    window.scrollTo({ top: 0 });
    el.focus({ preventScroll: true });
    document.getElementById("live").textContent = (ctx.title || "Page") + " loaded";
    document.dispatchEvent(new CustomEvent("routed", { detail: { key: match.key } }));
  } catch (e) {
    if (my !== token) return;
    if (e && e.status === 401) return navigate(loginUrl(), { replace: true });
    console.error(e);
    mount(el, failure(e, render));
    document.title = "Error · Verity";
  }
}
export function start() { window.addEventListener("hashchange", render); render(); }
