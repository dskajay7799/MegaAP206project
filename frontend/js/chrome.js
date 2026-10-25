// Site chrome: demo banner, header (nav, search, cart/wishlist/account), mobile menu, footer.
import { h, icon, mount, $ } from "./dom.js";
import { state, on, isAdmin } from "./store.js";
import { navigate, parse } from "./router.js";
import { openAssistant } from "./assistant.js";
import { post } from "./api.js";
import { applySession } from "./store.js";
import { toast, toastError } from "./ui.js";

const NAV = [["/shop", "Shop"], ["/smartmatch", "SmartMatch"], ["/basket", "Budget basket"], ["/compare", "Compare"]];
const logoMark = () => { const s = icon("x"); s.innerHTML = '<rect width="32" height="32" rx="9" fill="#0b1026"/><path d="M7 9l9 15 9-15" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="25" cy="8" r="3.2" fill="#c8f560"/>'; s.setAttribute("viewBox", "0 0 32 32"); s.setAttribute("stroke", "none"); s.setAttribute("fill", "none"); return s; };

function banner() {
  const el = $("#banner");
  if (!state.meta?.synthetic_data || sessionStorage.getItem("verity.banner") === "off") return mount(el);
  mount(el, h("div", { class: "demo-banner", role: "note" }, h("span", null, h("b", null, "Demo store."), " Products, prices, ratings, stock and imagery are synthetic. Checkout never takes payment."), h("button", { type: "button", onclick: () => { sessionStorage.setItem("verity.banner", "off"); mount(el); } }, "Dismiss")));
}

function header() {
  const cartBadge = h("span", { class: "badge", hidden: true }), wishBadge = h("span", { class: "badge", hidden: true });
  const menu = h("div", { class: "mnav", id: "mnav" });
  const search = (cls) => { const f = h("form", { class: cls, role: "search", onsubmit: (e) => { e.preventDefault(); const q = new FormData(e.target).get("q").trim(); document.getElementById("hdr").classList.remove("mnav-open"); navigate("/shop" + (q ? "?q=" + encodeURIComponent(q) : "")); } },
    h("label", { class: "sr-only", for: cls + "-q" }, "Search products"), h("input", { id: cls + "-q", name: "q", type: "search", placeholder: "Search products, brands, uses…", autocomplete: "off", maxlength: 100 }));
    if (cls === "hsearch") f.append(h("button", { type: "submit", "aria-label": "Search" }, icon("search"))); return f; };
  const burger = h("button", { class: "ibtn menu-btn", type: "button", "aria-label": "Menu", "aria-expanded": "false", "aria-controls": "mnav", onclick: () => { const o = $("#hdr").classList.toggle("mnav-open"); burger.setAttribute("aria-expanded", String(o)); } }, icon("menu"));
  const acct = h("a", { class: "ibtn", href: "#/account", "aria-label": "Account" }, icon("user"));
  const wish = h("a", { class: "ibtn hide-s", href: "#/account/wishlist", "aria-label": "Wishlist" }, icon("heart"), wishBadge);
  const cart = h("a", { class: "ibtn", href: "#/cart", "aria-label": "Cart" }, icon("cart"), cartBadge);
  const nav = h("nav", { class: "nav", "aria-label": "Main" }, NAV.map(([to, t]) => h("a", { href: "#" + to, "data-to": to }, t)));
  const paint = () => {
    const n = state.cart?.items_count || 0, w = state.wishlist.size;
    const was = cartBadge.textContent; cartBadge.textContent = n; cartBadge.hidden = !n; cart.setAttribute("aria-label", `Cart, ${n} item${n === 1 ? "" : "s"}`);
    if (was !== String(n) && was !== "") { cartBadge.classList.remove("bump"); void cartBadge.offsetWidth; cartBadge.classList.add("bump"); }
    wishBadge.textContent = w; wishBadge.hidden = !w;
    acct.setAttribute("aria-label", state.user ? `Account of ${state.user.name}` : "Sign in");
    if (state.user) acct.setAttribute("title", state.user.name); else acct.removeAttribute("title");
    $$nav(); menuBuild();
  };
  const $$nav = () => { const p = parse().path; nav.querySelectorAll("a").forEach((a) => { if (p.startsWith(a.dataset.to)) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }); };
  const close = () => { $("#hdr").classList.remove("mnav-open"); burger.setAttribute("aria-expanded", "false"); };
  const menuBuild = () => mount(menu, search("msearch"), ...NAV.map(([to, t]) => h("a", { href: "#" + to, onclick: close }, t)),
    h("a", { href: "#/account", onclick: close }, state.user ? "My account" : "Sign in or create account"), h("a", { href: "#/account/wishlist", onclick: close }, "Wishlist"),
    isAdmin() ? h("a", { href: "#/admin", onclick: close }, "Admin dashboard") : null,
    state.user ? h("button", { class: "linklike", type: "button", onclick: signOut }, "Sign out") : null);
  on("cart", paint); on("session", paint); on("wishlist", paint); document.addEventListener("routed", () => { $$nav(); close(); });
  mount($("#hdr"), h("div", { class: "wrap hdr-in" }, burger, h("a", { class: "logo", href: "#/", "aria-label": "Verity home" }, logoMark(), "Verity"), nav, search("hsearch"), h("span", { class: "spacer" }),
    h("div", { class: "hactions" }, h("button", { class: "ask-btn", type: "button", onclick: () => openAssistant({}) }, icon("spark"), h("span", null, "Ask Verity")), wish, acct, cart)), menu);
  paint();
}
export async function signOut() {
  try { applySession(await post("/api/auth/logout")); toast("You've been signed out"); navigate("/"); const { refreshCart } = await import("./store.js"); refreshCart(); } catch (e) { toastError(e); }
}

function footer() {
  const pol = (state.meta?.policy_sections || []).map((s) => h("li", null, h("a", { href: "#/policies" }, s.title)));
  const col = (title, ...items) => h("div", null, h("h4", null, title), h("ul", null, ...items));
  const li = (to, t) => h("li", null, h("a", { href: "#" + to }, t));
  mount($("#ftr"), h("div", { class: "wrap" }, h("div", { class: "ftr-grid" },
    h("div", null, h("a", { class: "logo", href: "#/", style: { color: "#fff" } }, logoMark(), "Verity"), h("p", { style: { "margin-top": "14px", "max-width": "34ch" } }, "A shopping assistant that shows its evidence. It answers only from the catalogue and store policy, and says so when it can't.")),
    col("Shop", li("/shop", "All products"), li("/smartmatch", "SmartMatch"), li("/basket", "Budget basket"), li("/compare", "Compare studio")),
    col("Help & policies", ...pol, li("/policies", "Delivery, returns & warranty")),
    col("Verity", li("/about", "How Verity works"), li("/privacy", "Privacy"), li("/account", "Your account"), isAdmin() ? li("/admin", "Admin") : null)),
    h("div", { class: "fine" }, h("span", null, state.meta?.synthetic_data ? "Demo store: synthetic products, prices and images. No real payments." : "© Verity"), h("span", null, "Prices include taxes (demo)."))));
}
export function buildChrome() { banner(); header(); footer(); on("session", footer); }
