import { h, icon, mount, fmtDateTime, debounce, qs } from "../dom.js";
import { get, post, put, patch, del } from "../api.js";
import { lineChart, barChart, donut } from "../charts.js";
import { field, busy, applyFieldErrors, toast, toastError, openDialog, confirmDialog, errorState, notice, statusClass } from "../ui.js";
import { navigate } from "../router.js";

const TABS = [["overview", "Overview"], ["products", "Products"], ["orders", "Orders"], ["customers", "Customers"], ["categories", "Categories"], ["system", "AI & health"]];
export default async function render(ctx) {
  const tab = ctx.tab || "overview";
  ctx.title = "Admin";
  const body = h("div");
  ({ overview, products, orders, customers, categories, system }[tab] || overview)(body).catch((e) => mount(body, errorState(e, () => navigate("/admin/" + tab, { replace: true }))));
  return h("div", { class: "wrap section" }, h("div", { class: "row spread" }, h("h1", { class: "h2" }, "Admin"), h("span", { class: "badge-s" }, "Administrator")),
    h("nav", { class: "tabs", "aria-label": "Admin sections", style: { margin: "14px 0 22px" } }, TABS.map(([k, t]) => h("a", { href: "#/admin/" + k, class: "atab", "aria-current": k === tab ? "page" : null }, t))), body);
}
const money = (v) => "₹" + Number(v).toLocaleString("en-IN");
async function overview(host) {
  let demo = true;
  const draw = async () => {
    const [s, c] = await Promise.all([get("/api/admin/summary" + qs({ include_demo: demo ? 1 : 0 })), get("/api/admin/charts" + qs({ include_demo: demo ? 1 : 0 }))]);
    const card = (t, v, sub) => h("div", { class: "card stat" }, h("div", { class: "muted small" }, t), h("div", { class: "price big num" }, v), sub ? h("div", { class: "small muted" }, sub) : null);
    mount(host, h("label", { class: "check" }, Object.assign(h("input", { type: "checkbox", checked: demo, onchange: (e) => { demo = e.target.checked; draw(); } })), "Include demo-seeded data"), s.demo.note && demo ? notice("demo", s.demo.note) : null,
      h("div", { class: "grid", style: { margin: "16px 0" } }, card("Orders", s.orders.total, `${s.orders.active} active · ${s.orders.cancelled} cancelled`), card("Order value", s.order_value.text, s.order_value.rule), card("Revenue", s.revenue.text, s.revenue.rule), card("Customers", s.customers), card("Products", s.products.active, `${s.products.inactive} hidden`), card("Stock alerts", s.inventory.out_of_stock + s.inventory.low_stock, `${s.inventory.out_of_stock} out · ${s.inventory.low_stock} low`)),
      h("div", { class: "cmp-two" }, h("div", { class: "card" }, lineChart({ title: "Sales, last 30 days", points: c.sales.map((d) => ({ x: d.date.slice(5), y: d.value })), fmt: money })), h("div", { class: "card" }, barChart({ title: "Orders by status", data: c.orders_by_status.map((d) => ({ label: d.label, value: d.value })) }))),
      h("div", { class: "cmp-two", style: { "margin-top": "18px" } }, h("div", { class: "card" }, donut({ title: "Products by category", data: c.category_distribution })), h("div", { class: "card" }, barChart({ title: "Top products by units ordered", horizontal: true, data: c.top_products.map((d) => ({ label: d.label, value: d.value })) }))),
      h("div", { class: "cmp-two", style: { "margin-top": "18px" } }, h("div", { class: "card" }, barChart({ title: "Stock distribution", data: c.stock_distribution })), h("div", { class: "card" }, h("h2", { class: "h3" }, "Low stock"), s.inventory.low_items.length ? h("ul", { class: "plain small" }, s.inventory.low_items.map((i) => h("li", null, `${i.title}: ${i.stock_qty} left`))) : h("p", { class: "muted" }, "Nothing is running low."))));
  };
  await draw();
}
async function products(host) {
  const q = h("input", { class: "input", type: "search", placeholder: "Search products…", "aria-label": "Search products" }), list = h("div");
  const load = async () => { const d = await get("/api/admin/products" + qs({ q: q.value, page_size: 30 })); mount(list, h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, ["Product", "Category", "Price", "Stock", "Status", ""].map((t) => h("th", null, t)))),
    h("tbody", null, d.items.map((p) => h("tr", null, h("td", null, h("b", null, p.title), h("div", { class: "small muted" }, p.id)), h("td", null, p.category), h("td", { class: "num" }, p.price_text), h("td", { class: "num" }, p.stock_qty ?? p.stock_text), h("td", null, p.is_active ? "Active" : h("span", { class: "badge-s warn" }, "Hidden")), h("td", null, h("button", { class: "btn btn-sm btn-ghost", type: "button", onclick: () => edit(p) }, "Edit"))))))), h("p", { class: "small muted" }, `${d.total} products`)); };
  q.addEventListener("input", debounce(load, 300));
  mount(host, h("div", { class: "row spread" }, q, h("button", { class: "btn", type: "button", onclick: () => edit(null) }, icon("plus"), "New product")), h("div", { style: { "margin-top": "14px" } }, list));
  function edit(p) {
    const f = { id: field({ label: "ID", name: "id", value: p?.id || "", readonly: !!p }), title: field({ label: "Title", name: "title", value: p?.title || "" }), brand: field({ label: "Brand", name: "brand", value: p?.brand || "" }), category: field({ label: "Category", name: "category", value: p?.category || "" }), subcategory: field({ label: "Subcategory", name: "subcategory", value: p?.subcategory || "" }),
      price: field({ label: "Price (₹)", name: "price", type: "number", value: p?.price ?? "" }), stock_qty: field({ label: "Stock (blank if it has options)", name: "stock_qty", type: "number", value: p?.stock_qty_raw ?? "", min: 0 }), rating: field({ label: "Rating (0–5)", name: "rating", type: "number", step: "0.1", value: p?.rating ?? "" }),
      description: field({ label: "Description", name: "description", rows: 3, value: p?.description || "" }), images: field({ label: "Images (https:// or /assets/… one per line)", name: "images", rows: 3, value: (p?.images || []).join("\n") }), use_cases: field({ label: "Uses (comma separated)", name: "use_cases", value: (p?.use_cases || []).join(", ") }),
      specs: field({ label: "Specs (JSON)", name: "specs", rows: 4, value: JSON.stringify(p?.specs_raw || {}) }) };
    const flags = { featured: h("input", { type: "checkbox", checked: p?.featured }), is_active: h("input", { type: "checkbox", checked: p ? p.is_active : true }) };
    const form = h("form", { class: "stack", onsubmit: async (e) => { e.preventDefault(); Object.values(f).forEach((x) => x.setError(""));
      let specs; try { specs = JSON.parse(f.specs.input.value || "{}"); } catch { return f.specs.setError("Not valid JSON."); }
      const v = (k) => f[k].input.value, body = { title: v("title"), brand: v("brand"), category: v("category"), subcategory: v("subcategory"), price: v("price"), rating: v("rating"), description: v("description"), specs, images: v("images").split("\n").map((s) => s.trim()).filter(Boolean), use_cases: v("use_cases").split(",").map((s) => s.trim()).filter(Boolean), featured: flags.featured.checked, is_active: flags.is_active.checked };
      if (!p?.has_variants) body.stock_qty = v("stock_qty");
      if (!p) body.id = v("id");
      await busy(e.submitter, async () => { try { await (p ? put("/api/admin/products/" + encodeURIComponent(p.id), body) : post("/api/admin/products", body)); d.close(); toast("Saved. The assistant now uses the new data."); load(); } catch (er) { applyFieldErrors(f, er) || toastError(er); } }); } },
      ...Object.values(f), h("label", { class: "check" }, flags.featured, "Featured"), h("label", { class: "check" }, flags.is_active, "Visible in the store"),
      h("div", { class: "btn-row" }, h("button", { class: "btn", type: "submit" }, "Save"), p ? h("button", { class: "btn btn-danger", type: "button", onclick: async () => { if (await confirmDialog({ title: "Delete this product?", text: "Past orders keep their own copy of the details.", confirm: "Delete", danger: true })) { await del("/api/admin/products/" + encodeURIComponent(p.id)).catch(toastError); d.close(); load(); } } }, "Delete") : null));
    const d = openDialog({ title: p ? "Edit product" : "New product", body: form, side: true, wide: true });
  }
  load();
}
async function orders(host) {
  const st = h("select", { class: "select", "aria-label": "Filter by status" }, ["", "placed", "processing", "shipped", "delivered", "cancelled"].map((s) => h("option", { value: s }, s || "All statuses"))), list = h("div");
  const load = async () => { const d = await get("/api/admin/orders" + qs({ status: st.value, page_size: 30 })); mount(list, d.items.length ? h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, ["Order", "Date", "Customer", "Status", "Total", ""].map((t) => h("th", null, t)))), h("tbody", null, d.items.map((o) => h("tr", null, h("td", null, o.order_number, o.is_demo_seeded ? h("span", { class: "badge-s demo", style: { "margin-left": "6px" } }, "demo") : null), h("td", null, fmtDateTime(o.created_at)), h("td", null, o.ship_to.name), h("td", null, h("span", { class: "badge-s " + statusClass(o.status) }, o.status_label)), h("td", { class: "r num" }, o.total_text), h("td", null, o.next_statuses.length ? h("button", { class: "btn btn-sm btn-ghost", type: "button", onclick: () => move(o) }, "Update") : null)))))) : h("p", { class: "muted" }, "No orders yet. Checkout is disabled in this demo, so only demo-seeded orders appear.")); };
  function move(o) { const sel = h("select", { class: "select" }, o.next_statuses.map((s) => h("option", { value: s }, s))); const d = openDialog({ title: `Order ${o.order_number}`, body: h("div", { class: "stack" }, h("p", null, "Current status: ", h("b", null, o.status_label)), sel, h("button", { class: "btn", type: "button", onclick: async () => { try { await patch(`/api/admin/orders/${o.order_number}/status`, { status: sel.value }); d.close(); load(); } catch (e) { toastError(e); } } }, "Update status")) }); }
  st.addEventListener("change", load);
  mount(host, st, h("div", { style: { "margin-top": "14px" } }, list)); await load();
}
async function customers(host) {
  const d = await get("/api/admin/customers?page_size=50");
  mount(host, h("p", { class: "muted small" }, d.note), h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, ["Name", "Email", "Orders", "Spent"].map((t) => h("th", null, t)))), h("tbody", null, d.items.map((u) => h("tr", null, h("td", null, u.name, u.is_demo ? h("span", { class: "badge-s demo", style: { "margin-left": "6px" } }, "demo") : null), h("td", null, u.email), h("td", { class: "num" }, u.orders), h("td", { class: "num" }, u.spent_text))))))); 
}
async function categories(host) {
  const d = await get("/api/admin/categories"), name = field({ label: "New category", name: "name" });
  mount(host, h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, ["Category", "Products", ""].map((t) => h("th", null, t)))), h("tbody", null, d.items.map((c) => h("tr", null, h("td", null, c.name), h("td", { class: "num" }, c.products), h("td", null, h("button", { class: "linklike", type: "button", onclick: async () => { const n = prompt("Rename category", c.name); if (n) { await put("/api/admin/categories/" + c.id, { name: n }).catch(toastError); categories(host); } } }, "Rename"), " ", h("button", { class: "linklike", type: "button", onclick: async () => { await del("/api/admin/categories/" + c.id).then(() => categories(host), toastError); } }, "Delete")))))),
    h("form", { class: "row", style: { "margin-top": "16px", "align-items": "end" }, onsubmit: async (e) => { e.preventDefault(); try { await post("/api/admin/categories", { name: name.input.value }); categories(host); } catch (er) { applyFieldErrors({ name }, er) || toastError(er); } } }, name, h("button", { class: "btn", type: "submit" }, "Add")));
}
async function system(host) {
  const [hl, ai] = await Promise.all([get("/api/admin/health"), get("/api/admin/ai")]);
  const kv = (o) => h("dl", { class: "kv" }, Object.entries(o).flatMap(([k, v]) => [h("dt", null, k), h("dd", null, String(v))]));
  mount(host, h("div", { class: "cmp-two" }, h("div", { class: "card" }, h("h2", { class: "h3" }, "Service health"), kv({ Database: `${hl.database.ok ? "OK" : "DOWN"} (${hl.database.kind}, migration ${hl.database.migration})`, Catalogue: `${hl.catalogue.source}${hl.catalogue.synthetic ? " (synthetic)" : ""}`, "Products indexed": hl.catalogue.products_indexed, "AI mode": hl.ai.mode, "Question logging": hl.chat_logging ? "on" : "off", Email: hl.email_configured ? "configured" : "not configured", Uptime: hl.uptime_seconds + " s" })),
    h("div", { class: "card" }, h("h2", { class: "h3" }, "Assistant usage"), ai.note ? h("p", { class: "muted" }, ai.note) : kv(Object.fromEntries(ai.by_status.map((s) => [s.status, `${s.count} · ${s.avg_latency_ms} ms avg`]))))));
}
