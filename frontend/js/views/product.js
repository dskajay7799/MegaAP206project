import { h, icon, mount, clear, COLOUR_HEX, inr, fmtDate } from "../dom.js";
import { get, put, del } from "../api.js";
import { state, toggleCompare, inCompare, trackView, guestRecent, on } from "../store.js";
import { productCard, img, productAlt, stars, addToCart, busy, toast, toastError, notice, wishToggle, shareLink, errorState, needLogin } from "../ui.js";
import { openAssistant } from "../assistant.js";
import { navigate } from "../router.js";
import { lineChart } from "../charts.js";


function gallery(p) {
  const imgs = p.images.length ? p.images : [null];
  let i = 0, zoom = false;
  const main = img(imgs[0], productAlt(p), { eager: true, cls: "gal-img" });
  const stageEl = h("div", { class: "gal-stage", tabindex: "0", role: "group", "aria-roledescription": "carousel", "aria-label": `${p.title} images` }, main);
  const counter = h("span", { class: "gal-count small", "aria-live": "polite" });
  const labels = ["Front view", "Angled view", "Close-up detail"];
  const thumbs = imgs.map((src, k) => h("button", { class: "thumb", type: "button", "aria-label": `Show image ${k + 1}: ${labels[k] || "view"}`, "aria-current": k === 0 ? "true" : null, onclick: () => show(k) }, img(src, "", {})));
  const show = (k) => {
    i = (k + imgs.length) % imgs.length;
    main.classList.add("swap");
    setTimeout(() => { main.src = imgs[i] || main.src; main.alt = `${productAlt(p)} (${labels[i] || "view " + (i + 1)})`; main.classList.remove("swap"); }, 130);
    thumbs.forEach((t, n) => (n === i ? t.setAttribute("aria-current", "true") : t.removeAttribute("aria-current")));
    counter.textContent = `${i + 1} / ${imgs.length}`;
  };
  const setZoom = (on_, e) => { zoom = on_; stageEl.classList.toggle("zoomed", on_); if (on_ && e) move(e); };
  const move = (e) => { const r = stageEl.getBoundingClientRect(); main.style.setProperty("--zx", (((e.clientX - r.left) / r.width) * 100).toFixed(1) + "%"); main.style.setProperty("--zy", (((e.clientY - r.top) / r.height) * 100).toFixed(1) + "%"); };
  stageEl.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse" && zoom) move(e); });
  stageEl.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") setZoom(true, e); });
  stageEl.addEventListener("pointerleave", () => setZoom(false));
  stageEl.addEventListener("click", (e) => { if (e.pointerType !== "mouse") setZoom(!zoom, e); });
  stageEl.addEventListener("keydown", (e) => { if (e.key === "ArrowRight") { e.preventDefault(); show(i + 1); } if (e.key === "ArrowLeft") { e.preventDefault(); show(i - 1); } });
  counter.textContent = `1 / ${imgs.length}`;
  const nav = imgs.length > 1 ? [h("button", { class: "gal-nav prev", type: "button", "aria-label": "Previous image", onclick: () => show(i - 1) }, icon("chevL")), h("button", { class: "gal-nav next", type: "button", "aria-label": "Next image", onclick: () => show(i + 1) }, icon("chevR"))] : [];
  return h("div", { class: "gallery" }, h("div", { class: "gal-main" }, stageEl, ...nav, h("span", { class: "badge-s demo gal-note" }, "Illustration"), counter), imgs.length > 1 ? h("div", { class: "thumbs" }, thumbs) : null);
}

function variantPicker(p, onChange) {
  const names = Object.keys(p.options || {});
  const sel = {};
  const wrap = h("div", { class: "variants" });
  const match = () => p.variants.filter((v) => names.every((n) => !sel[n] || v.options[n] === sel[n]));
  const full = () => (names.length && names.every((n) => sel[n]) ? p.variants.find((v) => names.every((n) => v.options[n] === sel[n])) : null);
  const paint = () => {
    mount(wrap, names.map((n) => {
      const vals = p.options[n];
      const avail = (val) => p.variants.some((v) => v.options[n] === val && v.available && names.every((m) => m === n || !sel[m] || v.options[m] === sel[m]));
      return h("div", { class: "vgroup", role: "radiogroup", "aria-label": n }, h("div", { class: "label" }, n.charAt(0).toUpperCase() + n.slice(1), ": ", h("b", null, sel[n] || "choose")),
        h("div", { class: "chips" }, vals.map((val) => {
          const ok = avail(val), on_ = sel[n] === val, cls = (n === "colour" ? "dot-chip" : "chip") + (ok ? "" : " na") + (on_ && n !== "colour" ? " on" : "");
          return h("button", { type: "button", class: cls, role: "radio", "aria-checked": String(on_), "aria-pressed": String(on_), disabled: !ok, title: ok ? val : `${val} (sold out)`, "aria-label": ok ? val : `${val}, sold out`, style: n === "colour" ? { "--c": COLOUR_HEX[val.toLowerCase()] || "#999" } : null,
            onclick: () => { sel[n] = on_ ? "" : val; paint(); onChange(full(), sel); } }, n === "colour" ? null : val);
        })));
    }));
  };
  paint();
  return { node: wrap, selected: full, sel, names, paint };
}

export default async function render(ctx) {
  let p;
  try { p = await get(`/api/products/${encodeURIComponent(ctx.id)}`); }
  catch (e) { if (e.status === 404) return h("div", { class: "wrap section" }, h("div", { class: "state" }, icon("search"), h("h2", null, "We couldn't find that product"), h("p", null, `“${ctx.id}” isn't in the catalogue. It may have been removed.`), h("a", { class: "btn", href: "#/shop" }, "Browse the shop"))); throw e; }
  ctx.title = p.title;
  trackView(p.id);
  const oos = p.stock === "out_of_stock";
  let qty = 1, variant = null;
  const priceEl = h("span", { class: "price big" }, p.price_text), stockEl = h("span", { class: "stock " + (oos ? "bad" : "ok") });
  const qtyOut = h("output", { "aria-live": "polite" }, "1");
  const cap = () => Math.min(state.meta?.commerce?.max_qty || 10, p.has_variants ? (variant ? variant.stock_qty : 10) : (p.stock_qty ?? 10));
  const paintStock = () => {
    const q_ = p.has_variants ? (variant ? variant.stock_qty : null) : p.stock_qty;
    mount(stockEl, p.has_variants && !variant ? [icon("info"), oos ? "Sold out" : "Choose options to see availability"] : q_ === 0 || oos ? [icon("alert"), "Out of stock"] : [icon("check"), q_ != null && q_ <= 5 ? `Only ${q_} left` : "In stock"]);
    stockEl.className = "stock " + (q_ === 0 || oos ? "bad" : q_ != null && q_ <= 5 ? "warn" : "ok");
  };
  const minus = h("button", { type: "button", "aria-label": "Decrease quantity", onclick: () => setQty(qty - 1) }, "−"), plus = h("button", { type: "button", "aria-label": "Increase quantity", onclick: () => setQty(qty + 1) }, "+");
  const setQty = (n) => { qty = Math.max(1, Math.min(n, cap() || 1)); qtyOut.textContent = qty; minus.disabled = qty <= 1; plus.disabled = qty >= cap(); };
  const picker = p.has_variants ? variantPicker(p, (v) => { variant = v; if (v) priceEl.textContent = v.price_text; setQty(qty); paintStock(); addBtn.disabled = !canBuy(); buyBtn.disabled = !canBuy(); }) : null;
  const canBuy = () => !oos && (!p.has_variants || (variant && variant.available));
  const errBox = h("div", { "aria-live": "polite" });
  const addBtn = h("button", { class: "btn", type: "button", disabled: !canBuy(), onclick: (e) => {
    if (p.has_variants && !variant) { mount(errBox, notice("warn", "Choose " + picker.names.join(" and ") + " first.", "alert")); return; }
    mount(errBox); busy(e.currentTarget, () => addToCart(p, variant?.id, qty).catch(() => {})); } }, icon("cart"), oos ? "Sold out" : "Add to cart");
  const buyBtn = h("button", { class: "btn btn-ink", type: "button", disabled: !canBuy(), onclick: () => {       // demo: Buy now never starts a purchase or collects anything
    mount(errBox, notice("demo", "Checkout is disabled in this demo. Nothing was purchased and no payment details are collected. You can still add items to the cart.", "info"));
    toast("Checkout is disabled in this demo", { ms: 3500 }); } }, "Buy now");
  if (p.has_variants) { addBtn.removeAttribute("disabled"); buyBtn.removeAttribute("disabled"); if (oos) { addBtn.disabled = buyBtn.disabled = true; } }
  const heart = h("button", { class: "btn btn-ghost", type: "button", "aria-pressed": String(state.wishlist.has(p.id)), onclick: () => wishToggle(p.id, heart).then(() => paintHeart()) }, icon("heart"), h("span", null, "Save"));
  const paintHeart = () => { const on_ = state.wishlist.has(p.id); heart.setAttribute("aria-pressed", String(on_)); heart.querySelector("span").textContent = on_ ? "Saved" : "Save"; heart.classList.toggle("is-on", on_); };
  const cmp = h("button", { class: "btn btn-ghost", type: "button", "aria-pressed": String(inCompare(p.id)), onclick: () => { toggleCompare(p.id); paintCmp(); } }, icon("compare"), h("span", null, "Compare"));
  const paintCmp = () => { const on_ = inCompare(p.id); cmp.setAttribute("aria-pressed", String(on_)); cmp.querySelector("span").textContent = on_ ? "In compare" : "Compare"; cmp.classList.toggle("is-on", on_); };
  paintHeart(); paintCmp(); paintStock(); setQty(1);

  const lens = lensPanel(p);
  const pol = (p.policies || []).filter((s) => ["shipping", "returns", "return"].some((w) => s.title.toLowerCase().includes(w)));
  const info = h("div", { class: "pinfo" }, h("div", { class: "pbrand" }, p.brand || p.category, p.sku ? h("span", { class: "muted" }, ` · SKU ${p.sku}`) : null), h("h1", { class: "ptitle-h" }, p.title),
    h("div", { class: "row" }, stars(p.rating, p.rating_is_demo), p.rating_is_demo ? h("span", { class: "badge-s demo", title: "Synthetic catalogue data" }, "Demo rating") : null),
    h("div", { class: "row price-row" }, priceEl, p.mrp_text ? h("s", { class: "muted" }, p.mrp_text) : null, stockEl),
    p.highlights.length ? h("ul", { class: "ticks" }, p.highlights.map((t) => h("li", null, icon("check"), t))) : null,
    picker ? picker.node : null, errBox,
    !oos ? h("div", { class: "row buybox" }, h("div", { class: "qty", role: "group", "aria-label": "Quantity" }, minus, qtyOut, plus), addBtn, buyBtn) : h("div", { class: "row buybox" }, addBtn),
    h("div", { class: "btn-row" }, heart, cmp, h("button", { class: "btn btn-ghost", type: "button", onclick: () => shareLink(p.title, location.href.split("#")[0] + "#/product/" + encodeURIComponent(p.id)) }, icon("share"), "Share")),
    h("button", { class: "ask-card", type: "button", onclick: () => openAssistant({ product: p }) }, icon("spark"), h("span", null, h("b", null, "Ask Verity about this product"), h("small", null, "Specs, stock and policy, answered from the record, with the source shown."))),
    h("div", { class: "delivery" }, h("div", null, icon("truck"), h("span", null, h("b", null, "Delivery"), h("small", null, `Standard 3–6 business days. Free above ₹${state.meta?.commerce?.free_shipping_above ?? 999}.`))),
      h("div", null, icon("shield"), h("span", null, h("b", null, "Returns & warranty"), h("small", null, "Return window and warranty are set by the store policy.", " ", h("a", { href: "#/policies" }, "Read the policy"))))));

  const specs = p.specs.length || Object.keys(p.attributes).length ? h("section", { class: "card", "aria-labelledby": "specs-h" }, h("h2", { id: "specs-h" }, "Specifications"),
    h("dl", { class: "kv" }, (p.specs.length ? p.specs.map((s) => [s.label, s.display]) : Object.entries(p.attributes)).flatMap(([k, v]) => [h("dt", null, k), h("dd", null, v)]),
      p.specs.length ? Object.entries(p.attributes).filter(([k]) => !["Colour", "Size"].includes(k) && !p.specs.some((s) => s.label === k)).flatMap(([k, v]) => [h("dt", null, k), h("dd", null, v)]) : [])) : null;
  const desc = h("section", { class: "card", "aria-labelledby": "desc-h" }, h("h2", { id: "desc-h" }, "About this product"), h("p", null, p.description || "No description is listed."),
    p.use_cases.length ? h("p", { class: "muted", style: { "margin-top": "10px" } }, "Listed uses: ", p.use_cases.join(", "), ".") : null);
  const policies = pol.length ? h("section", { class: "card", "aria-labelledby": "pol-h" }, h("h2", { id: "pol-h" }, "Delivery & returns"), pol.map((s) => h("div", { style: { "margin-top": "10px" } }, h("b", null, s.title), h("p", { class: "muted" }, s.text), h("code", { class: "small" }, s.id)))) : null;
  const histHost = h("div"), relHost = h("div"), recHost = h("div");
  historyPanel(p, histHost);
  if (p.related.length) mount(relHost, h("section", { class: "section-tight", "aria-label": "Related products" }, h("h2", null, "You might also like"), h("p", { class: "muted small" }, "Chosen by type and listed uses, not by what other shoppers bought."), h("div", { class: "grid g4", style: { "margin-top": "16px" } }, p.related.slice(0, 4).map(productCard))));
  recentPanel(p.id, recHost);
  const node = h("div", { class: "wrap" }, h("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, h("a", { href: "#/" }, "Home"), "›", h("a", { href: "#/shop?category=" + encodeURIComponent(p.category) }, p.category), p.subcategory ? ["›", h("a", { href: `#/shop?category=${encodeURIComponent(p.category)}&subcategory=${encodeURIComponent(p.subcategory)}` }, p.subcategory)] : null),
    h("div", { class: "pdp" }, gallery(p), info), h("div", { class: "pdp-lower" }, h("div", { class: "stack", style: { "--gap": "20px" } }, desc, specs, policies, histHost), h("div", null, lens)), relHost, recHost);
  const unsub = [on("wishlist", paintHeart), on("compare", paintCmp)];
  return { node, destroy: () => unsub.forEach((f) => f()) };
}

function lensPanel(p) {
  const host = h("section", { class: "card lens", "aria-labelledby": "lens-h" });
  const budget = h("input", { type: "number", min: 0, inputmode: "numeric", placeholder: "e.g. 3000", "aria-label": "Your budget in rupees" }), need = h("input", { type: "text", maxlength: 120, placeholder: "e.g. long battery life", "aria-label": "What matters to you" });
  const out = h("div", { "aria-live": "polite" });
  const run = async (e) => { e && e.preventDefault(); mount(out, h("div", { class: "sk", style: { height: "120px" } })); try { const d = await get(`/api/products/${encodeURIComponent(p.id)}/value-lens?budget=${encodeURIComponent(budget.value)}&need=${encodeURIComponent(need.value)}`);
    mount(out, h("ul", { class: "factors light" }, d.factors.map((f) => h("li", null, h("span", { class: "vd " + f.verdict }, f.verdict), h("span", null, h("b", null, f.label), h("small", { class: "muted" }, f.detail))))), h("p", { class: "small" }, d.summary), d.notes.map((n) => h("p", { class: "small muted" }, n)), h("p", { class: "small muted" }, d.disclaimer)); } catch (er) { mount(out, errorState(er, run)); } };
  mount(host, h("h2", { id: "lens-h" }, icon("spark"), "Value Lens"), h("p", { class: "muted small" }, "Why this might (or might not) be good value for you, from catalogue facts only."),
    h("form", { class: "lens-form", onsubmit: run }, h("label", null, h("span", { class: "small" }, "Budget (₹)"), budget), h("label", null, h("span", { class: "small" }, "What matters"), need), h("button", { class: "btn btn-sm", type: "submit" }, "Explain")), out);
  run();
  return host;
}

async function historyPanel(p, host) {
  try {
    const d = await get(`/api/products/${encodeURIComponent(p.id)}/price-history`);
    const watch = state.user ? h("form", { class: "row watch", onsubmit: async (e) => { e.preventDefault(); const t = e.target.elements.t.value; try { await put(`/api/account/watches/${encodeURIComponent(p.id)}`, { target_price: t }); toast("Watching. Check your account page to see when it's reached.", { ms: 5000 }); } catch (er) { toastError(er); } } },
      h("label", { class: "small", for: "wt" }, "Watch for a price at or below ₹"), h("input", { id: "wt", name: "t", type: "number", min: 1, required: true, class: "input", style: { width: "120px", "min-height": "40px" } }), h("button", { class: "btn btn-sm btn-ghost", type: "submit" }, "Set watch"), h("span", { class: "small muted" }, "Checked when you open your account. No alerts are sent.")) : null;
    mount(host, h("section", { class: "card", "aria-labelledby": "ph-h" }, h("h2", { id: "ph-h" }, "Price history"),
      d.points.length >= 2 ? [d.has_simulated ? notice("demo", "Some earlier points are simulated demo data, not real market prices. They are drawn in the chart table as “simulated”.", "info") : null,
        lineChart({ title: "Price over time", points: d.points.map((x) => ({ x: fmtDate(x.at, { day: "numeric", month: "short" }), y: x.price })), fmt: (v) => inr(v), area: false, markers: true,
          summary: `${d.points.length} price points; ${d.recorded_count} recorded.` })] : h("p", { class: "muted" }, "Only one price has been recorded so far, so there's no history to show. Verity doesn't make one up."), watch));
  } catch { /* history is optional */ }
}

async function recentPanel(id, host) {
  try {
    let items;
    if (state.user) items = (await get("/api/account/recent")).items; else { const ids = guestRecent(); items = ids.length ? (await get("/api/products?ids=" + ids.join(",") + "&page_size=12")).items : []; }
    items = items.filter((x) => x.id !== id).slice(0, 4);
    if (items.length) mount(host, h("section", { class: "section-tight", "aria-label": "Recently viewed" }, h("h2", null, "Recently viewed"), h("div", { class: "grid g4", style: { "margin-top": "16px" } }, items.map(productCard))));
  } catch { /* optional */ }
}
