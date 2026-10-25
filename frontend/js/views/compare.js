import { h, icon, mount, debounce, qs } from "../dom.js";
import { get, post } from "../api.js";
import { state, setCompare, on } from "../store.js";
import { img, productAlt, stars, toast, toastError, emptyState, errorState, notice, addToCart, busy, shareLink } from "../ui.js";
import { radar } from "../charts.js";
import { navigate } from "../router.js";

export default async function render(ctx) {
  ctx.title = "Compare";
  const qIds = (ctx.query.get("ids") || "").split(",").filter(Boolean);
  if (qIds.length) setCompare(qIds);
  const host = h("div"), weights = {};
  let useCase = ctx.query.get("use") || "";
  const ids = () => state.compare;
  const url = () => `#/compare?ids=${ids().map(encodeURIComponent).join(",")}`;
  async function load() {
    if (ids().length < 2) return empty();
    mount(host, h("div", { class: "sk", style: { height: "320px" } }));
    try { const d = await get("/api/compare" + qs({ ids: ids().join(","), use_case: useCase, weights: Object.entries(weights).map(([k, v]) => `${k}:${v}`).join(",") })); paint(d); } catch (e) { mount(host, errorState(e, load)); }
  }
  const empty = () => mount(host, emptyState({ ic: "compare", title: ids().length ? "Pick one more product" : "Compare products side by side", text: "Tap the compare icon on any product card, or search below. You can compare up to 4.", actions: [h("a", { class: "btn", href: "#/shop" }, "Browse products")] }), adder());
  function adder() {
    const out = h("ul", { class: "pick-list" });
    const input = h("input", { type: "search", class: "input", placeholder: "Search a product to add…", "aria-label": "Search a product to add" });
    input.addEventListener("input", debounce(async () => { const q = input.value.trim(); if (q.length < 2) return mount(out); try { const d = await get("/api/products?page_size=6&q=" + encodeURIComponent(q)); mount(out, d.items.filter((p) => !ids().includes(p.id)).map((p) => h("li", null, h("button", { type: "button", class: "pick", onclick: () => { if (ids().length >= 4) return toast("You can compare up to 4 products.", { kind: "bad" }); setCompare([...ids(), p.id]); navigate(url().slice(1), { replace: true }); } }, img(p.image, ""), h("span", null, p.title), h("b", { class: "num" }, p.price_text))))); } catch { /* ignore */ } }, 250));
    return h("div", { class: "card adder" }, h("label", { class: "label", for: "cmp-add" }, "Add a product"), (input.id = "cmp-add", input), out);
  }
  function paint(d) {
    const s = d.studio, cols = s.columns, n = cols.length;
    const head = h("div", { class: "cmp-head", style: { "--n": n } }, cols.map((c, i) => h("div", { class: "cmp-col card" }, h("button", { class: "ibtn rm", type: "button", "aria-label": `Remove ${c.title}`, onclick: () => { setCompare(ids().filter((x) => x !== c.id)); navigate(url().slice(1), { replace: true }); } }, icon("x")),
      h("a", { href: `#/product/${encodeURIComponent(c.id)}` }, img(cols[i].image, productAlt(c))), h("a", { class: "ptitle", href: `#/product/${encodeURIComponent(c.id)}` }, c.title), stars(c.rating, c.rating_is_demo),
      h("div", { class: "price num" }, c.price_text), h("div", { class: "small " + (c.stock === "out_of_stock" ? "" : "muted") }, c.stock_text),
      s.price.bars ? h("div", { class: "bar " + (s.price.cheapest.includes(i) ? "lime" : "") }, h("i", { style: { "--w": (s.price.bars[i] ?? 0) * 100 + "%" } })) : null,
      h("button", { class: "btn btn-sm", type: "button", disabled: c.stock !== "in_stock" || d.cards[i]?.has_variants, onclick: (e) => busy(e.currentTarget, () => addToCart(d.cards[i]).catch(() => {})) }, d.cards[i]?.has_variants ? "Choose options on page" : "Add to cart"))));
    const rows = s.rows.map((r) => h("tr", { class: r.differs ? "diff" : "" }, h("th", { scope: "row" }, r.label, r.unit ? h("small", { class: "muted" }, ` (${r.unit})`) : null),
      r.values.map((v, i) => h("td", { class: (r.best.includes(i) ? "best " : "") + (r.worst.includes(i) ? "worst " : "") + (v == null ? "na" : "") }, v == null ? "Not listed" : v, r.bars && r.bars[i] != null ? h("div", { class: "bar", "aria-hidden": "true" }, h("i", { style: { "--w": r.bars[i] * 100 + "%" } })) : null, r.best.includes(i) ? h("span", { class: "vd good" }, "best") : null))));
    const wbox = s.criteria.length ? h("div", { class: "card" }, h("h2", { class: "h3" }, "What matters to you?"), h("p", { class: "muted small" }, "Drag to weight each factor (0 = ignore). Scores update from the numbers below, not from a guess."),
      h("form", { class: "uc", onsubmit: (e) => { e.preventDefault(); useCase = e.target.elements.u.value.trim(); load(); } }, h("input", { name: "u", class: "input", value: useCase, placeholder: "Your use case, e.g. long battery for commuting", maxlength: 160, "aria-label": "Use case" }), h("button", { class: "btn btn-sm", type: "submit" }, "Apply")),
      h("div", { class: "sliders" }, s.criteria.map((c) => h("label", { class: "slider" }, h("span", null, c.label), h("input", { type: "range", min: 0, max: 5, step: 1, value: c.weight, "aria-label": `Weight for ${c.label}`, oninput: debounce((e) => { weights[c.id] = e.target.value; load(); }, 350) }), h("output", null, c.weight))))) : null;
    const rec = s.recommendation ? h("div", { class: "card dark rec" }, h("div", { class: "row" }, icon("spark"), h("h2", { class: "h3" }, "Recommendation")), h("p", null, s.recommendation.text), h("p", { class: "small muted" }, s.recommendation.basis),
      h("div", { class: "score-row" }, s.scores.map((sc, i) => h("div", { class: "sc" }, h("div", { class: "ring", style: { "--p": sc.score ?? 0, "--s": "58px" } }, h("b", null, Math.round(sc.score ?? 0))), h("small", null, cols[i].title.split(" ").slice(0, 2).join(" ")), sc.coverage < 1 ? h("small", { class: "muted" }, `${Math.round(sc.coverage * 100)}% data`) : null)))) : null;
    const rad = s.radar ? radar({ title: "Where they differ", axes: s.radar.axes.map((a) => ({ label: a.label + (a.better === "lower" ? " (lower is better)" : ""), raw: a.values.map((v) => v + (a.unit ? " " + a.unit : "")) })), series: cols.map((c, i) => ({ name: c.title, values: s.radar.axes.map((a) => a.scaled[i]) })), summary: s.radar.note })
      : h("p", { class: "small muted" }, icon("info"), " ", s.radar_reason);
    mount(host, head, s.warnings.map((w) => h("div", { style: { margin: "14px 0" } }, notice("warn", w, "alert"))), rec ? h("div", { style: { margin: "20px 0" } }, rec) : null,
      h("div", { class: "table-wrap cmp-table" }, h("table", null, h("caption", { class: "sr-only" }, "Aligned specifications"), h("thead", null, h("tr", null, h("th", null, ""), cols.map((c) => h("th", { scope: "col" }, c.title)))), h("tbody", null, rows))),
      h("div", { class: "cmp-two" }, h("div", { class: "card" }, rad), wbox),
      h("div", { class: "cmp-pl grid", style: { "margin-top": "20px" } }, cols.map((c) => h("div", { class: "card" }, h("h3", null, c.title), s.pros[c.id].length ? h("ul", { class: "ticks" }, s.pros[c.id].map((t) => h("li", null, icon("check"), t))) : h("p", { class: "muted small" }, "No standout strengths on the compared specs."),
        s.limits[c.id].length ? h("ul", { class: "ticks bad" }, s.limits[c.id].map((t) => h("li", null, icon("alert"), t))) : null))),
      h("div", { class: "btn-row", style: { "margin-top": "22px" } }, h("button", { class: "btn btn-ghost", type: "button", onclick: () => shareLink("Verity comparison", location.href.split("#")[0] + url()) }, icon("share"), "Share"),
        h("button", { class: "btn btn-ghost", type: "button", onclick: async () => { if (!state.user) return toast("Sign in to save comparisons", { action: { label: "Sign in", onClick: () => navigate("/login?next=" + encodeURIComponent("/compare?ids=" + ids().join(","))) } }); try { await post("/api/account/comparisons", { product_ids: ids() }); toast("Comparison saved to your account"); } catch (e) { toastError(e); } } }, "Save comparison"),
        h("button", { class: "linklike", type: "button", onclick: () => { setCompare([]); navigate("/compare", { replace: true }); } }, "Clear")), h("div", { style: { "margin-top": "20px" } }, ids().length < 4 ? adder() : null));
  }
  load();
  const off = on("compare", () => {});
  return { node: h("div", { class: "wrap section" }, h("div", { class: "section-head" }, h("div", null, h("h1", { class: "h2" }, "Compare studio"), h("p", null, "Aligned specs, honest bars and a weighted recommendation you control. Only like-for-like numbers are compared."))), host), destroy: off };
}
