import { h, icon, mount } from "../dom.js";
import { post } from "../api.js";
import { img, productAlt, toast, errorState, notice, addToCart, busy, emptyState } from "../ui.js";

const EX = [["Study setup", 5000], ["Gym starter kit", 6000], ["Headphones and a backpack", 5000], ["Travel kit", 7000]];
export default async function render(ctx) {
  ctx.title = "Budget basket";
  const budget = h("input", { class: "input", type: "number", min: 50, max: 1000000, inputmode: "numeric", value: ctx.query.get("budget") || "5000", "aria-label": "Total budget in rupees" });
  const purpose = h("input", { class: "input", type: "text", maxlength: 200, value: ctx.query.get("purpose") || "", placeholder: "e.g. study setup, or headphones and a backpack", "aria-label": "What is the basket for" });
  const out = h("div", { "aria-live": "polite" });
  async function run() {
    mount(out, h("div", { class: "sk", style: { height: "260px" } }));
    try { paint(await post("/api/basket", { budget: +budget.value, purpose: purpose.value })); } catch (e) { mount(out, e.status === 400 ? notice("warn", e.message, "alert") : errorState(e, run)); }
  }
  function paint(r) {
    if (r.status === "clarify") return mount(out, h("div", { class: "card clar" }, icon("info"), h("h2", { class: "h3" }, r.clarify.question), h("p", { class: "muted" }, r.clarify.reason), h("div", { class: "chips" }, r.clarify.options.map((o) => h("button", { class: "chip", type: "button", onclick: () => { purpose.value = o.append; run(); } }, o.label)))));
    if (r.status === "no_match" || !r.baskets.length) return mount(out, emptyState({ ic: "bag", title: "No basket fits", text: r.notes.join(" ") }));
    let cur = 0;
    const body = h("div");
    const tabs = h("div", { class: "tabs", role: "tablist" }, r.baskets.map((b, i) => h("button", { type: "button", role: "tab", "aria-selected": String(i === 0), onclick: (e) => { cur = i; tabs.querySelectorAll("button").forEach((x, k) => x.setAttribute("aria-selected", String(k === i))); show(); } }, b.label)));
    function show() {
      const b = r.baskets[cur], used = Math.min(100, (b.total / r.budget) * 100);
      mount(body, h("div", { class: "card bk-sum" }, h("div", { class: "row spread" }, h("div", null, h("div", { class: "muted small" }, "Total"), h("div", { class: "price big num" }, b.total_text)), h("div", null, h("div", { class: "muted small" }, "Remaining of " + r.budget_text), h("div", { class: "price big num", style: { color: "var(--ok)" } }, b.remaining_text)), h("div", { class: "small muted" }, `${b.slots_filled} of ${b.slots_total} product types filled`)),
        h("div", { class: "bar ink", role: "img", "aria-label": `${Math.round(used)}% of budget used` }, h("i", { style: { "--w": used + "%" } }))),
        h("ul", { class: "bk-items" }, b.items.map((i) => h("li", { class: "card" }, h("a", { href: `#/product/${encodeURIComponent(i.product.id)}`, class: "m-img" }, img(i.product.image, productAlt(i.product))),
          h("div", { class: "grow" }, h("div", { class: "pbrand" }, i.slot), h("a", { class: "ptitle", href: `#/product/${encodeURIComponent(i.product.id)}` }, i.product.title), h("ul", { class: "plain small" }, i.why.map((w) => h("li", null, w))),
            i.missing.length ? h("p", { class: "small", style: { color: "var(--warn)" } }, "Not listed: " + i.missing.join("; ")) : null,
            i.alternatives.length ? h("details", { class: "small" }, h("summary", null, `${i.alternatives.length} alternative${i.alternatives.length > 1 ? "s" : ""} that still fit`), h("ul", { class: "plain" }, i.alternatives.map((a) => h("li", null, h("a", { href: `#/product/${encodeURIComponent(a.id)}` }, a.title), ` ${a.price_text} (${a.delta_text})`)))) : null),
          h("div", { class: "tr" }, h("div", { class: "price num" }, i.price_text), h("small", { class: "muted" }, `fit ${i.fit ?? "n/a"}`), !i.product.has_variants && i.product.stock === "in_stock" ? h("button", { class: "btn btn-sm", type: "button", onclick: (e) => busy(e.currentTarget, () => addToCart(i.product).catch(() => {})) }, "Add") : h("a", { class: "btn btn-sm btn-ghost", href: `#/product/${encodeURIComponent(i.product.id)}` }, "Options"))))),
        h("div", { class: "btn-row bk-addrow" }, h("button", { class: "btn", type: "button", onclick: async (e) => busy(e.currentTarget, async () => { let n = 0; for (const i of b.items) if (!i.product.has_variants) { try { await addToCart(i.product, null, 1, { quiet: true }); n++; } catch { /* toast shown */ } } toast(n ? `Added ${n} item${n > 1 ? "s" : ""} to your cart` + (n < b.items.length ? ". Items with sizes or colours need choosing on their page." : "") : "These items need options chosen on their pages"); }) }, icon("cart"), "Add items without options to cart")));
    }
    show();
    mount(out, tabs, h("div", { style: { "margin-top": "16px" } }, body),
      r.slots.some((s) => s.status !== "filled") ? h("div", { class: "card", style: { "margin-top": "16px" } }, h("h2", { class: "h3" }, "Product types not in this basket"), h("ul", { class: "plain small" }, r.slots.filter((s) => s.status !== "filled").map((s) => h("li", null, h("b", null, s.slot), ": ", s.reason)))) : null,
      r.over_budget.length ? h("div", { class: "card", style: { "margin-top": "16px" } }, h("h2", { class: "h3" }, "Over budget, and by how much"), h("ul", { class: "plain small" }, r.over_budget.map((o) => h("li", null, h("a", { href: `#/product/${encodeURIComponent(o.id)}` }, o.title), ` (${o.price_text}): ${o.reason}`)))) : null,
      r.notes.length ? h("div", { style: { "margin-top": "16px" } }, notice("info", r.notes.join(" "))) : null);
  }
  const form = h("form", { class: "card bk-form", onsubmit: (e) => { e.preventDefault(); run(); } }, h("div", { class: "field-row bk-fields" }, h("div", { class: "field" }, h("label", null, "Total budget (₹)"), budget), h("div", { class: "field" }, h("label", null, "What is it for?"), purpose)),
    h("div", { class: "row spread" }, h("div", { class: "chips" }, EX.map(([p, b]) => h("button", { class: "chip", type: "button", onclick: () => { purpose.value = p; budget.value = b; run(); } }, `${p} · ₹${b.toLocaleString("en-IN")}`))), h("button", { class: "btn", type: "submit" }, "Build my basket")));
  if (purpose.value) run();
  return h("div", { class: "wrap section" }, h("div", { class: "section-head" }, h("div", null, h("h1", { class: "h2" }, "Smart budget basket"), h("p", null, "Give Verity a budget and a purpose. It picks one product per type from what the catalogue lists for that use, shows the total and what's left, and tells you what didn't fit."))), form, h("div", { style: { "margin-top": "22px" } }, out));
}
