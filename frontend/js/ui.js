// Shared UI: toasts, dialogs, product card (with pointer tilt), images with fallback, form fields, state blocks.
import { h, icon, mount, $, $$ } from "./dom.js";
import { state, toggleWish, toggleCompare, inCompare, setCart, on } from "./store.js";
import { post, ApiError } from "./api.js";
import { navigate, loginUrl } from "./router.js";

const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const fine = matchMedia("(hover: hover) and (pointer: fine)");

/* ---------- toasts ---------- */
export function toast(msg, { kind = "ok", action, ms = 4600 } = {}) {
  const box = document.getElementById("toasts");
  const t = h("div", { class: "toast " + kind, role: kind === "bad" ? "alert" : "status" }, h("span", null, msg));
  if (action) t.append(h("button", { type: "button", onclick: () => { action.onClick(); t.remove(); } }, action.label));
  box.append(t);
  setTimeout(() => t.remove(), ms);
  while (box.children.length > 3) box.firstChild.remove();
}
export const toastError = (e) => toast(e?.message || "Something went wrong.", { kind: "bad", ms: 6500 });

/* ---------- dialogs (focus trapped, ESC to close, restores focus) ---------- */
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
export function openDialog({ title, body, footer, side = false, wide = false, cls = "", label, onClose }) {
  const prev = document.activeElement;
  const titleId = "dlg-" + Math.random().toString(36).slice(2, 8);
  const close = () => { overlay.remove(); document.body.style.removeProperty("overflow"); document.removeEventListener("keydown", key, true); if (prev && prev.focus) prev.focus(); onClose && onClose(); };
  const sheet = h("div", { class: "sheet" + (wide ? " wide" : "") + (cls ? " " + cls : ""), role: "dialog", "aria-modal": "true", "aria-labelledby": titleId },
    h("div", { class: "sheet-h" }, h("h2", { id: titleId }, title), h("button", { class: "ibtn", type: "button", "aria-label": "Close", onclick: close }, icon("x"))),
    h("div", { class: "sheet-b" }, body), footer ? h("div", { class: "sheet-f" }, footer) : null);
  const overlay = h("div", { class: "overlay" + (side ? "" : " center"), onmousedown: (e) => { if (e.target === overlay) close(); } }, sheet);
  const key = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); return; }
    if (e.key !== "Tab") return;
    const f = $$(FOCUSABLE, sheet).filter((x) => x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener("keydown", key, true);
  document.body.append(overlay);
  document.body.style.overflow = "hidden";
  (sheet.querySelector("[autofocus]") || sheet.querySelector(".sheet-b " + FOCUSABLE.split(",").join(",.sheet-b ")) || sheet.querySelector(".ibtn")).focus();
  return { close, sheet };
}
export function confirmDialog({ title, text, confirm = "Confirm", danger = false }) {
  return new Promise((res) => {
    let done = false;
    const fin = (v) => { if (!done) { done = true; res(v); } };
    const d = openDialog({ title, body: h("p", null, text), onClose: () => fin(false),
      footer: [h("button", { class: "btn btn-ghost", type: "button", onclick: () => d.close() }, "Cancel"),
        h("button", { class: "btn" + (danger ? " btn-danger" : ""), type: "button", autofocus: true, onclick: () => { fin(true); d.close(); } }, confirm)] });
  });
}

/* ---------- loading helper ---------- */
export async function busy(btn, fn) {
  if (btn.classList.contains("is-loading")) return;
  btn.classList.add("is-loading"); btn.setAttribute("aria-busy", "true"); btn.disabled = true;
  try { return await fn(); } finally { btn.classList.remove("is-loading"); btn.removeAttribute("aria-busy"); btn.disabled = false; }
}

/* ---------- images ---------- */
const FALLBACK = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600"><rect width="600" height="600" fill="#ebe8df"/><g fill="none" stroke="#9a9fb5" stroke-width="10" stroke-linejoin="round"><path d="M180 240 300 180l120 60v130l-120 60-120-60V240Z"/><path d="m180 240 120 60 120-60M300 300v130"/></g><text x="300" y="500" text-anchor="middle" font-family="Arial,sans-serif" font-size="26" fill="#6b7089">Image unavailable</text></svg>');
export function img(src, alt, { eager = false, cls = "" } = {}) {
  const el = h("img", { src: src || FALLBACK, alt: alt || "", width: 600, height: 600, loading: eager ? "eager" : "lazy", decoding: "async", class: cls });
  el.addEventListener("error", () => { if (el.src !== FALLBACK) el.src = FALLBACK; }, { once: true });
  return el;
}
export const productAlt = (p) => `Illustration of ${p.title}`;

/* ---------- ratings ---------- */
export function stars(r, demo) {
  if (r == null) return h("span", { class: "stars muted" }, "No rating");
  return h("span", { class: "stars", title: demo ? "Demo rating: synthetic catalogue data, not customer reviews" : "Catalogue rating", "aria-label": `Rated ${r} out of 5${demo ? " (demo rating)" : ""}` }, icon("star"), h("span", { class: "num" }, r.toFixed(1)), demo ? h("span", { class: "muted small" }, "demo") : null);
}

/* ---------- pointer tilt (fine pointers only, never with reduced motion) ---------- */
export function tilt(el, max = 7) {
  if (!fine.matches || reduced.matches) return;
  el.addEventListener("pointermove", (e) => {
    const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    el.style.setProperty("--rx", ((x - .5) * max * 2).toFixed(2)); el.style.setProperty("--ry", ((.5 - y) * max * 2).toFixed(2));
    el.style.setProperty("--mx", (x * 100).toFixed(1) + "%"); el.style.setProperty("--my", (y * 100).toFixed(1) + "%");
  });
  el.addEventListener("pointerleave", () => { el.style.setProperty("--rx", 0); el.style.setProperty("--ry", 0); });
}

/* ---------- cart / wishlist / compare actions ---------- */
export async function addToCart(product, variantId = null, qty = 1, { quiet = false } = {}) {
  try {
    const body = { product_id: product.id, quantity: qty }; if (variantId) body.variant_id = variantId;
    const cart = await post("/api/cart/items", body);
    setCart(cart);
    if (!quiet) toast(`Added “${product.title}” to your cart`, { action: { label: "View cart", onClick: () => navigate("/cart") } });
    return cart;
  } catch (e) { toastError(e); throw e; }
}
export function needLogin(msg = "Sign in to continue") {
  toast(msg, { action: { label: "Sign in", onClick: () => navigate(loginUrl()) } });
}
export async function wishToggle(id, btn) {
  try {
    const on_ = await toggleWish(id);
    if (btn) btn.setAttribute("aria-pressed", String(on_));
    toast(on_ ? "Saved to your wishlist" : "Removed from your wishlist", { ms: 2500 });
  } catch (e) { if (e instanceof ApiError && e.status === 401) needLogin("Sign in to save items to your wishlist"); else toastError(e); }
}

// One listener each (not one per card) keeps every visible compare/heart button in sync without leaking subscriptions across re-renders.
on("compare", () => document.querySelectorAll("[data-cmp]").forEach((b) => { const x = inCompare(b.dataset.cmp); b.setAttribute("aria-pressed", String(x)); b.classList.toggle("btn-ink", x); b.classList.toggle("btn-ghost", !x); }));
on("wishlist", () => document.querySelectorAll("[data-heart]").forEach((b) => b.setAttribute("aria-pressed", String(state.wishlist.has(b.dataset.heart)))));
on("session", () => document.querySelectorAll("[data-heart]").forEach((b) => b.setAttribute("aria-pressed", String(state.wishlist.has(b.dataset.heart)))));

export function productCard(p) {
  const oos = p.stock === "out_of_stock";
  const heart = h("button", { class: "pheart", type: "button", "data-heart": p.id, "aria-pressed": String(state.wishlist.has(p.id)), "aria-label": `Save ${p.title} to wishlist`, onclick: (e) => { e.preventDefault(); wishToggle(p.id, heart); } }, icon("heart"));
  const cmp = h("button", { class: "btn btn-ghost pcmp", type: "button", "data-cmp": p.id, "aria-pressed": String(inCompare(p.id)), "aria-label": `Compare ${p.title}`, title: "Add to compare" }, icon("compare"));
  cmp.classList.toggle("btn-ink", inCompare(p.id)); cmp.classList.toggle("btn-ghost", !inCompare(p.id));
  cmp.addEventListener("click", () => { if (!toggleCompare(p.id)) toast(`You can compare up to ${state.meta?.max_compare || 4} products.`, { kind: "bad" }); });
  const add = p.has_variants || oos
    ? h("a", { class: "btn btn-ink", href: `#/product/${encodeURIComponent(p.id)}` }, oos ? "Details" : "Choose options")
    : h("button", { class: "btn", type: "button", onclick: (e) => busy(e.currentTarget, () => addToCart(p).catch(() => {})) }, icon("cart"), "Add");
  const card = h("article", { class: "pcard" + (oos ? " oos" : ""), "data-id": p.id },
    h("a", { class: "pmedia", href: `#/product/${encodeURIComponent(p.id)}`, tabindex: "-1", "aria-hidden": "true" }, img(p.image, productAlt(p)),
      h("div", { class: "pbadges" }, (p.badges || []).map((b) => h("span", { class: "badge-s " + (b.id === "sold-out" ? "bad" : b.id === "low-stock" ? "warn" : b.id === "new" ? "new" : "") }, b.label)))),
    heart,
    h("div", { class: "pbody" }, h("div", { class: "pbrand" }, p.brand || p.category), h("a", { class: "ptitle", href: `#/product/${encodeURIComponent(p.id)}` }, p.title),
      stars(p.rating, p.rating_is_demo),
      h("div", { class: "prow" }, h("span", { class: "price" }, p.price_text, p.mrp_text ? h("s", null, p.mrp_text) : null), h("span", { class: "small " + (oos ? "" : "muted") }, p.stock_text)),
      h("div", { class: "pacts" }, add, cmp)),
    h("span", { class: "glare" }));
  tilt(card);
  return card;
}

/* ---------- state blocks ---------- */
export const skeletonGrid = (n = 8) => h("div", { class: "grid", "aria-busy": "true", "aria-label": "Loading products" }, ...Array.from({ length: n }, () => h("div", { class: "sk sk-card" })));
export function emptyState({ ic = "search", title, text, actions = [] }) {
  return h("div", { class: "state" }, icon(ic), h("h3", null, title), text ? h("p", null, text) : null, actions.length ? h("div", { class: "btn-row", style: { "justify-content": "center" } }, actions) : null);
}
export function errorState(err, retry) {
  return h("div", { class: "state err", role: "alert" }, icon("alert"), h("h3", null, "That didn't load"), h("p", null, err?.message || "Something went wrong."), retry ? h("button", { class: "btn", type: "button", onclick: retry }, "Try again") : null);
}
export const notice = (kind, text, ic = "info") => h("div", { class: "notice " + kind, role: kind === "bad" ? "alert" : undefined }, icon(ic), h("div", null, text));

/* ---------- forms ---------- */
let uid = 0;
export function field({ label, name, type = "text", value = "", required = false, autocomplete, hint, rows, options, inputmode, maxlength, placeholder, min, max, step, readonly }) {
  const id = `f-${name}-${++uid}`;
  const errEl = h("div", { class: "err", id: id + "-err", hidden: true });
  let input;
  if (options) input = h("select", { id, name }, ...options.map((o) => h("option", { value: o.value ?? o, selected: String(o.value ?? o) === String(value) }, o.label ?? o)));
  else if (rows) input = h("textarea", { id, name, rows, maxlength, placeholder }, value);
  else input = h("input", { id, name, type, value, autocomplete, inputmode, maxlength, placeholder, min, max, step, readonly: readonly || null });
  if (required) input.setAttribute("required", "");
  if (hint) input.setAttribute("aria-describedby", id + "-hint");
  const wrap = h("div", { class: "field" }, h("label", { for: id }, label, required ? h("span", { class: "sr-only" }, " (required)") : null), type === "password" ? passwordWrap(input) : input,
    hint ? h("div", { class: "hint", id: id + "-hint" }, hint) : null, errEl);
  wrap.input = input;
  wrap.setError = (msg) => { errEl.hidden = !msg; mount(errEl, msg ? [icon("alert"), msg] : []); input.setAttribute("aria-invalid", msg ? "true" : "false"); if (msg) input.setAttribute("aria-describedby", id + "-err"); };
  return wrap;
}
function passwordWrap(input) {
  const btn = h("button", { type: "button", "aria-label": "Show password", "aria-pressed": "false", onclick: () => { const show = input.type === "password"; input.type = show ? "text" : "password"; btn.textContent = show ? "Hide" : "Show"; btn.setAttribute("aria-pressed", String(show)); btn.setAttribute("aria-label", show ? "Hide password" : "Show password"); } }, "Show");
  return h("div", { class: "pw" }, input, btn);
}
export function applyFieldErrors(fields, err) {
  let first = null;
  for (const [k, f] of Object.entries(fields)) { const m = err?.fields?.[k]; f.setError(m || ""); if (m && !first) first = f.input; }
  if (first) first.focus();
  return !!first;
}
export const statusClass = (s) => ({ placed: "", processing: "warn", shipped: "warn", delivered: "ok", cancelled: "bad" }[s] || "");
export function shareLink(title, url) {
  if (navigator.share) return navigator.share({ title, url }).catch(() => {});
  return navigator.clipboard?.writeText(url).then(() => toast("Link copied to clipboard"), () => toast(url));
}
