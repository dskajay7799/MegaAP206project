import { h, icon, mount, clear, debounce, COLOUR_HEX, qs } from "../dom.js";
import { get } from "../api.js";
import { state } from "../store.js";
import { productCard, skeletonGrid, emptyState, errorState, openDialog } from "../ui.js";
import { setQuery, parse, navigate } from "../router.js";
import { openAssistant } from "../assistant.js";

const SORTS = [["", "Relevance"], ["price_asc", "Price: low to high"], ["price_desc", "Price: high to low"], ["rating", "Rating"], ["newest", "Newest"], ["name", "Name A–Z"]];
const KEYS = ["q", "category", "subcategory", "brand", "colour", "size", "use", "featured", "in_stock", "min_price", "max_price", "min_rating", "sort", "page"];
const list = (v) => (v ? v.split(",").filter(Boolean) : []);

function filterPanel(q, commit, meta) {
  const draft = { ...q };
  const set = (k, v, instant = true) => { draft[k] = v; if (k !== "page") draft.page = ""; if (instant) commit(draft); };
  const toggle = (k, val) => { const l = list(draft[k]); const i = l.indexOf(val); i >= 0 ? l.splice(i, 1) : l.push(val); set(k, l.join(",")); };
  const group = (title, ...kids) => h("fieldset", { class: "fgroup" }, h("legend", null, title), ...kids);
  const cats = meta.categories || [];
  const catBtns = h("div", { class: "cat-list" }, h("button", { type: "button", class: "chip" + (!draft.category ? " on" : ""), "aria-pressed": String(!draft.category), onclick: () => { set("subcategory", "", false); set("category", ""); } }, "All"),
    cats.map((c) => h("button", { type: "button", class: "chip" + (draft.category === c.name ? " on" : ""), "aria-pressed": String(draft.category === c.name), onclick: () => { set("subcategory", "", false); set("category", draft.category === c.name ? "" : c.name); } }, c.name, h("small", null, c.count))));
  const subs = (cats.find((c) => c.name === draft.category) || {}).subcategories || [];
  const min = h("input", { type: "number", min: 0, inputmode: "numeric", placeholder: "Min ₹", "aria-label": "Minimum price", value: draft.min_price || "" }), max = h("input", { type: "number", min: 0, inputmode: "numeric", placeholder: "Max ₹", "aria-label": "Maximum price", value: draft.max_price || "" });
  const applyPrice = debounce(() => { draft.min_price = min.value; draft.max_price = max.value; draft.page = ""; commit(draft); }, 500);
  min.addEventListener("input", applyPrice); max.addEventListener("input", applyPrice);
  const check = (k, label, on) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: on, onchange: (e) => set(k, e.target.checked ? "1" : "") }), label);
  const brands = meta.brands || [];
  const ratingSel = h("select", { "aria-label": "Minimum rating", class: "select", onchange: (e) => set("min_rating", e.target.value) }, [["", "Any rating"], ["4", "4.0 & up"], ["4.4", "4.4 & up"]].map(([v, l]) => h("option", { value: v, selected: String(draft.min_rating || "") === v }, l)));
  const node = h("div", { class: "filters-in" }, group("Category", catBtns, subs.length ? h("div", { class: "chips", style: { "margin-top": "8px" } }, subs.map((s) => h("button", { type: "button", class: "chip" + (draft.subcategory === s.name ? " on" : ""), "aria-pressed": String(draft.subcategory === s.name), onclick: () => set("subcategory", draft.subcategory === s.name ? "" : s.name) }, s.name))) : null),
    group("Price (₹)", h("div", { class: "price-in" }, min, h("span", null, "–"), max), meta.price_max ? h("p", { class: "hint small muted" }, `Catalogue range ₹${Math.floor(meta.price_min)}–₹${Math.ceil(meta.price_max)}`) : null),
    group("Availability", check("in_stock", "In stock only", draft.in_stock === "1"), check("featured", "Featured only", draft.featured === "1")),
    brands.length ? group("Brand", h("div", { class: "brand-list" }, brands.map((b) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: list(draft.brand).includes(b), onchange: () => toggle("brand", b) }), b)))) : null,
    (meta.colours || []).length ? group("Colour", h("div", { class: "chips" }, meta.colours.map((c) => h("button", { type: "button", class: "dot-chip", style: { "--c": COLOUR_HEX[c.toLowerCase()] || "#999" }, title: c, "aria-label": c, "aria-pressed": String(list(draft.colour).includes(c)), onclick: (e) => { toggle("colour", c); e.currentTarget.setAttribute("aria-pressed", String(list(draft.colour).includes(c))); } })))) : null,
    (meta.sizes || []).length ? group("Size", h("div", { class: "chips" }, meta.sizes.map((s) => h("button", { type: "button", class: "chip" + (list(draft.size).includes(s) ? " on" : ""), "aria-pressed": String(list(draft.size).includes(s)), onclick: (e) => { toggle("size", s); e.currentTarget.classList.toggle("on"); e.currentTarget.setAttribute("aria-pressed", String(list(draft.size).includes(s))); } }, s)))) : null,
    group("Rating", ratingSel));
  node.draft = draft;
  return node;
}
const activeChips = (q, reset) => {
  const out = [];
  const add = (k, label, val) => out.push(h("button", { class: "chip chip-x", type: "button", "aria-label": `Remove filter ${label}`, onclick: () => setQuery({ [k]: val == null ? "" : val, page: "" }) }, label, h("span", { "aria-hidden": "true" }, "×")));
  if (q.q) add("q", `“${q.q}”`);
  if (q.category) add("category", q.category); if (q.subcategory) add("subcategory", q.subcategory);
  for (const k of ["brand", "colour", "size"]) list(q[k]).forEach((v) => add(k, v, list(q[k]).filter((x) => x !== v).join(",")));
  if (q.use) add("use", `Use: ${q.use}`);
  if (q.in_stock) add("in_stock", "In stock"); if (q.featured) add("featured", "Featured");
  if (q.min_price || q.max_price) { out.push(h("button", { class: "chip chip-x", type: "button", onclick: () => setQuery({ min_price: "", max_price: "", page: "" }) }, `₹${q.min_price || 0} – ${q.max_price ? "₹" + q.max_price : "any"}`, h("span", { "aria-hidden": "true" }, "×"))); }
  if (q.min_rating) add("min_rating", `${q.min_rating}★ & up`);
  return out;
};

export default async function render(ctx) {
  ctx.title = "Shop";
  const meta = state.meta || (await get("/api/meta"));
  const results = h("div", { "aria-live": "polite" }), head = h("div", { class: "results-head" }), chipsEl = h("div", { class: "chips active-chips" }), side = h("aside", { class: "filters", "aria-label": "Filters" });
  let q = {}, ctrl = null, lastKey = "";
  const readQ = (query) => { q = {}; KEYS.forEach((k) => { const v = query.get(k); if (v) q[k] = v; }); };
  const commit = (draft) => { const o = {}; KEYS.forEach((k) => (o[k] = draft[k] || "")); setQuery(o); };
  const buildSide = () => { const p = filterPanel(q, commit, meta); mount(side, h("div", { class: "row spread filters-h" }, h("h2", null, "Filters"), h("button", { class: "linklike", type: "button", onclick: () => navigate("/shop", { replace: true }) }, "Reset all")), p); };
  const load = async () => {
    const key = JSON.stringify(q);
    if (key === lastKey) return;
    lastKey = key;
    if (ctrl) ctrl.abort(); ctrl = new AbortController();
    mount(results, skeletonGrid(8));
    const params = { ...q, page_size: 12 };
    try {
      const d = await get("/api/products" + qs(params), { signal: ctrl.signal });
      const active = activeChips(q);
      mount(chipsEl, active, active.length ? h("button", { class: "linklike small", type: "button", onclick: () => navigate("/shop", { replace: true }) }, "Clear all") : null);
      mount(head, h("p", { class: "muted", role: "status" }, d.total ? `${d.total} product${d.total === 1 ? "" : "s"}` + (q.q ? ` for “${q.q}”` : "") : ""),
        h("label", { class: "sort" }, h("span", null, "Sort by"), h("select", { class: "select", onchange: (e) => setQuery({ sort: e.target.value, page: "" }) }, SORTS.map(([v, l]) => h("option", { value: v, selected: (q.sort || "") === v }, l)))));
      if (!d.items.length) return mount(results, emptyState({ title: "No products match these filters", text: q.q ? `Nothing in the catalogue matches “${q.q}” with these filters. Try fewer filters, or ask Verity what's closest.` : "Try removing a filter or widening the price range.",
        actions: [h("button", { class: "btn", type: "button", onclick: () => navigate("/shop", { replace: true }) }, "Reset filters"), h("button", { class: "btn btn-ghost", type: "button", onclick: () => openAssistant({ prompt: q.q || "show me products" }) }, icon("spark"), "Ask Verity")] }));
      mount(results, h("div", { class: "grid" }, d.items.map(productCard)), d.pages > 1 ? pager(d.page, d.pages) : null);
    } catch (e) { if (e.name === "AbortError") return; lastKey = ""; mount(results, errorState(e, load)); }
  };
  const pager = (page, pages) => {
    const go = (n) => { setQuery({ page: n > 1 ? n : "" }); window.scrollTo({ top: 0, behavior: "smooth" }); };
    const nums = [...new Set([1, page - 1, page, page + 1, pages].filter((n) => n >= 1 && n <= pages))].sort((a, b) => a - b);
    return h("nav", { class: "pager", "aria-label": "Pagination" }, h("button", { disabled: page <= 1, "aria-label": "Previous page", onclick: () => go(page - 1) }, icon("chevL")),
      ...nums.map((n, i) => [i && n - nums[i - 1] > 1 ? h("span", { "aria-hidden": "true" }, "…") : null, h("button", { "aria-current": n === page ? "page" : null, "aria-label": `Page ${n}`, onclick: () => go(n) }, n)]),
      h("button", { disabled: page >= pages, "aria-label": "Next page", onclick: () => go(page + 1) }, icon("chevR")));
  };
  const openFilters = () => {
    const wrap = h("div"); let cur = { ...q };
    const build = () => mount(wrap, filterPanel(cur, (d) => { cur = { ...d }; build(); }, meta));       // sheet applies on "Show results"; chips re-render as you pick
    build();
    const d = openDialog({ title: "Filters", side: true, body: wrap, footer: [h("button", { class: "btn btn-ghost", type: "button", onclick: () => { navigate("/shop", { replace: true }); d.close(); } }, "Reset"), h("button", { class: "btn", type: "button", onclick: () => { commit(cur); d.close(); } }, "Show results")] });
  };
  const update = (c) => { readQ(c.query); buildSide(); load(); mount(title, q.q ? `Results for “${q.q}”` : q.category || "All products"); };
  const title = h("h1", { class: "shop-title" });
  readQ(ctx.query); buildSide(); mount(title, q.q ? `Results for “${q.q}”` : q.category || "All products");
  const node = h("div", { class: "wrap section" }, h("div", { class: "shop-top" }, title, h("button", { class: "btn btn-ghost filters-open", type: "button", onclick: openFilters }, icon("filter"), "Filters")),
    h("div", { class: "shop" }, side, h("div", { class: "grow" }, chipsEl, head, results)));
  load();
  return { node, update, destroy: () => ctrl && ctrl.abort() };
}
