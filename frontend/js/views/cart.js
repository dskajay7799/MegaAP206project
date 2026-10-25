import { h, icon, mount, inr } from "../dom.js";
import { get, patch, del, ApiError } from "../api.js";
import { state, setCart, toggleWish } from "../store.js";
import { img, productAlt, productCard, toast, toastError, busy, emptyState, errorState, notice, openDialog, field } from "../ui.js";
import { openAssistant } from "../assistant.js";

export default async function render(ctx) {
  ctx.title = "Your cart";
  const host = h("div", { class: "wrap section" });
  let cart;
  const act = async (fn) => { try { cart = await fn(); setCart(cart); paint(); } catch (e) { toastError(e); load(); } };
  async function load() { try { cart = await get("/api/cart"); setCart(cart); paint(); } catch (e) { mount(host, errorState(e, load)); } }
  function line(l) {
    const url = `#/product/${encodeURIComponent(l.product_id)}`, bad = l.status !== "ok";
    return h("li", { class: "cline" + (bad ? " bad" : "") },
      h("a", { href: url, class: "cimg" }, img(l.image, `Illustration of ${l.title}`)),
      h("div", { class: "cmid" }, h("div", { class: "pbrand" }, l.brand), h("a", { class: "ptitle", href: url }, l.title),
        l.variant_label ? h("div", { class: "small muted" }, l.variant_label, " ", l.has_variants ? h("button", { class: "linklike", type: "button", onclick: () => changeVariant(l) }, "Change") : null) : null,
        bad ? h("div", { class: "form-error small" }, icon("alert"), l.message) : null,
        h("div", { class: "row small", style: { "margin-top": "6px" } }, h("button", { class: "linklike", type: "button", onclick: () => act(() => del(`/api/cart/items/${l.id}`)) }, "Remove"),
          h("button", { class: "linklike", type: "button", onclick: async () => { try { await toggleWish(l.product_id); await del(`/api/cart/items/${l.id}`).then((c) => { cart = c; setCart(c); paint(); }); toast("Moved to your wishlist"); } catch (e) { toastError(e); } } }, "Save for later"))),
      h("div", { class: "cqty" }, h("div", { class: "qty", role: "group", "aria-label": `Quantity for ${l.title}` },
        h("button", { type: "button", "aria-label": "Decrease", disabled: l.quantity <= 1, onclick: () => act(() => patch(`/api/cart/items/${l.id}`, { quantity: l.quantity - 1 })) }, "−"), h("output", null, l.quantity),
        h("button", { type: "button", "aria-label": "Increase", disabled: l.quantity >= l.max_qty, onclick: () => act(() => patch(`/api/cart/items/${l.id}`, { quantity: l.quantity + 1 })) }, "+")),
        h("div", { class: "price num" }, l.line_total_text), l.quantity > 1 ? h("div", { class: "small muted" }, `${l.unit_price_text} each`) : null));
  }
  async function changeVariant(l) {
    const p = await get(`/api/products/${encodeURIComponent(l.product_id)}`);
    const names = Object.keys(p.options), cur = p.variants.find((v) => v.id === l.variant_id), fs = {};
    const form = h("form", { class: "stack", onsubmit: async (e) => { e.preventDefault();
      const v = p.variants.find((x) => names.every((n) => x.options[n] === fs[n].input.value));
      if (!v || !v.available) return toast("That combination is sold out", { kind: "bad" });
      d.close(); act(() => patch(`/api/cart/items/${l.id}`, { variant_id: v.id })); } },
      ...names.map((n) => (fs[n] = field({ label: n[0].toUpperCase() + n.slice(1), name: n, value: cur?.options[n], options: p.options[n] }))), h("button", { class: "btn", type: "submit" }, "Update"));
    const d = openDialog({ title: "Change option", body: form });
  }
  function paint() {
    if (!cart.lines.length) return mount(host, h("h1", null, "Your cart"), h("div", { style: { "margin-top": "24px" } }, emptyState({ ic: "cart", title: "Your cart is empty", text: "Add something you like, or describe what you need and Verity will find it.",
      actions: [h("a", { class: "btn", href: "#/shop" }, "Browse the shop"), h("button", { class: "btn btn-ghost", type: "button", onclick: () => openAssistant({}) }, "Ask Verity")] })));
    const free = cart.free_shipping_remaining_text;
    const sum = h("aside", { class: "card summary", "aria-label": "Order summary" }, h("h2", null, "Summary"),
      h("dl", { class: "kv tot" }, h("dt", null, `Items (${cart.items_count})`), h("dd", { class: "num" }, cart.subtotal_text), h("dt", null, "Shipping"), h("dd", { class: "num" }, cart.shipping_text), h("dt", null, h("b", null, "Total")), h("dd", { class: "num" }, h("b", null, cart.total_text))),
      free ? h("div", { class: "free-ship" }, h("div", { class: "small" }, `Add ${free} more for free shipping`), h("div", { class: "bar lime" }, h("i", { style: { "--w": Math.min(100, (cart.subtotal / (parseFloat(cart.free_shipping_threshold_text.replace(/[^\d.]/g, "")) || 999)) * 100) + "%" } }))) : h("div", { class: "small", style: { color: "var(--ok)" } }, "You've unlocked free shipping."),
      h("button", { class: "btn btn-ink btn-block", type: "button", onclick: () => { mount(note, notice("demo", "Checkout is disabled in this demo. Nothing is charged, no order is created, and no payment details are asked for.", "info")); toast("Checkout is disabled in this demo", { ms: 3500 }); } }, icon("lock"), "Checkout"),
      h("div", { "aria-live": "polite" }, note), h("a", { class: "btn btn-ghost btn-block", href: "#/shop" }, "Continue shopping"), h("p", { class: "small muted" }, cart.note));
    mount(host, h("div", { class: "row spread" }, h("h1", null, "Your cart"), h("button", { class: "linklike", type: "button", onclick: () => act(() => del("/api/cart")) }, "Clear cart")),
      cart.issues.length ? h("div", { style: { "margin-top": "16px" } }, notice("warn", "Some items need your attention before they can be bought.", "alert")) : null,
      h("div", { class: "cart-grid" }, h("ul", { class: "clines" }, cart.lines.map(line)), sum), sugg);
    loadSugg();
  }
  const note = h("div"), sugg = h("div");
  async function loadSugg() {
    try { const s = await get("/api/cart/suggestions"); if (s.items.length) mount(sugg, h("section", { class: "section-tight" }, h("h2", null, "Goes with what's in your cart"), h("p", { class: "muted small" }, s.note), h("div", { class: "grid g4", style: { "margin-top": "16px" } }, s.items.map((i) => h("div", null, productCard(i.product), h("p", { class: "small muted", style: { "margin-top": "6px" } }, i.reason)))))); } catch { /* optional */ }
  }
  mount(host, h("div", { class: "sk", style: { height: "260px" } }));
  load();
  return host;
}
