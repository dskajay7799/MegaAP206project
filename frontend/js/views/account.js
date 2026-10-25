import { h, icon, mount, fmtDate } from "../dom.js";
import { get, post, put, patch, del } from "../api.js";
import { state, applySession, setCompare, refreshCart } from "../store.js";
import { field, busy, applyFieldErrors, toast, toastError, productCard, emptyState, errorState, notice, confirmDialog, openDialog, statusClass } from "../ui.js";
import { donut, barChart } from "../charts.js";
import { navigate } from "../router.js";
import { signOut } from "../chrome.js";

const TABS = [["overview", "Overview"], ["saved", "Saved"], ["preferences", "Preferences"], ["profile", "Profile & security"], ["privacy", "Privacy"]];
export default async function render(ctx) {
  const tab = ctx.tab || "overview";
  ctx.title = "Account";
  const body = h("div");
  const dash = await get("/api/account/dashboard");
  const tabs = dash.orders_count ? [...TABS.slice(0, 2), ["orders", "Orders"], ...TABS.slice(2)] : TABS;
  const views = { overview, saved, preferences, profile, privacy, orders };
  (views[tab] || overview)(body, dash).catch((e) => mount(body, errorState(e, () => navigate("/account/" + tab, { replace: true }))));
  return h("div", { class: "wrap section" }, h("h1", { class: "h2" }, `Hello, ${state.user.name.split(" ")[0]}`),
    h("div", { class: "acct-grid" }, h("nav", { class: "acct-nav", "aria-label": "Account sections" }, tabs.map(([k, t]) => h("a", { href: "#/account/" + k, "aria-current": k === tab ? "page" : null }, t)), h("a", { href: "#/wishlist" }, "Wishlist"), h("button", { class: "linklike", type: "button", onclick: signOut }, "Sign out")), body));
}
async function overview(host, d) {
  const sp = d.spending, rec = await get("/api/recommendations").catch(() => ({ items: [], enough_data: false, reason: "" }));
  mount(host, h("div", { class: "grid g4" }, [["Wishlist", state.wishlist.size, "/wishlist"], ["Saved comparisons", d.comparisons_count, "/account/saved"], ["Orders", d.orders_count, "/account/orders"]].map(([t, n, to]) => h("a", { class: "card stat", href: "#" + to }, h("div", { class: "muted small" }, t), h("div", { class: "price big num" }, n)))),
    h("section", { class: "section-tight" }, h("h2", { class: "h3" }, "Picked for you"), rec.enough_data && rec.items.length ? [h("p", { class: "muted small" }, "Based on " + rec.basis.join(" and ") + "."), h("div", { class: "grid g4", style: { "margin-top": "14px" } }, rec.items.map((i) => h("div", null, productCard(i.product), h("p", { class: "small muted" }, i.reasons.join(" · ")))))]
      : emptyState({ ic: "spark", title: "No picks yet", text: rec.reason || "Set a few preferences and Verity will suggest products here.", actions: [h("a", { class: "btn", href: "#/account/preferences" }, "Set preferences")] })),
    sp.order_count ? h("section", { class: "section-tight" }, h("h2", { class: "h3" }, "Your spending"), h("p", { class: "muted small" }, `${sp.order_count} orders · ${sp.total_text} total · computed from your own orders.`),
      h("div", { class: "cmp-two" }, h("div", { class: "card" }, barChart({ title: "By month", data: sp.by_month.map((m) => ({ label: m.label, value: m.value })), fmt: (v) => "₹" + v.toLocaleString("en-IN") })), h("div", { class: "card" }, donut({ title: "By category", data: sp.by_category.map((m) => ({ label: m.label, value: m.value })), fmt: (v) => "₹" + v.toLocaleString("en-IN") })))) : null);
}
async function saved(host) {
  const [cmp, chats] = await Promise.all([get("/api/account/comparisons"), get("/api/account/chats")]);
  const refresh = () => saved(host);
  mount(host, h("section", null, h("h2", { class: "h3" }, "Saved comparisons"), cmp.items.length ? h("ul", { class: "plain saved" }, cmp.items.map((c) => h("li", { class: "card row spread" }, h("span", null, h("b", null, c.name), h("small", { class: "muted" }, " · " + c.product_ids.join(", "))), h("span", { class: "btn-row" }, h("a", { class: "btn btn-sm", href: "#/compare?ids=" + c.product_ids.join(","), onclick: () => setCompare(c.product_ids) }, "Open"), h("button", { class: "btn btn-sm btn-ghost", type: "button", onclick: async () => { await del("/api/account/comparisons/" + c.id).catch(toastError); refresh(); } }, "Delete"))))) : h("p", { class: "muted" }, "None yet. Save one from the compare page.")),
    h("section", { class: "section-tight" }, h("div", { class: "row spread" }, h("h2", { class: "h3" }, "Saved shortlists & chats"), chats.items.length ? h("button", { class: "linklike", type: "button", onclick: async () => { if (await confirmDialog({ title: "Delete all saved chats?", text: "This can't be undone.", confirm: "Delete all", danger: true })) { await del("/api/account/chats").catch(toastError); refresh(); } } }, "Delete all") : null),
      chats.items.length ? h("ul", { class: "plain saved" }, chats.items.map((c) => h("li", { class: "card" }, h("div", { class: "row spread" }, h("b", null, c.title), h("button", { class: "linklike small", type: "button", onclick: async () => { await del("/api/account/chats/" + c.id).catch(toastError); refresh(); } }, "Delete")),
        c.messages.slice(-2).map((m) => h("p", { class: "small " + (m.role === "user" ? "muted" : "") }, m.text)), c.product_ids.length ? h("a", { class: "small", href: "#/compare?ids=" + c.product_ids.slice(0, 4).join(","), onclick: () => setCompare(c.product_ids.slice(0, 4)) }, "Compare these") : null))) : h("p", { class: "muted" }, "None yet. Use “Save shortlist” under an assistant answer.")));
}
async function preferences(host) {
  const p = await get("/api/account/preferences"), sel = { categories: new Set(p.categories), requirements: new Set(p.requirements) };
  const chips = (k, items) => h("div", { class: "chips" }, items.map((v) => { const b = h("button", { type: "button", class: "chip", "aria-pressed": String(sel[k].has(v)), onclick: () => { sel[k].has(v) ? sel[k].delete(v) : sel[k].add(v); b.setAttribute("aria-pressed", String(sel[k].has(v))); } }, v); return b; }));
  const lo = field({ label: "Minimum budget (₹)", name: "lo", type: "number", value: p.budget_min ?? "" }), hi = field({ label: "Maximum budget (₹)", name: "hi", type: "number", value: p.budget_max ?? "" });
  mount(host, h("div", { class: "card stack" }, h("h2", { class: "h3" }, "Shopping preferences"), h("p", { class: "muted" }, p.note), h("div", null, h("div", { class: "label" }, "Categories you like"), chips("categories", p.options.categories)), h("div", null, h("div", { class: "label" }, "What you shop for"), chips("requirements", p.options.requirements)), h("div", { class: "field-row" }, lo, hi),
    h("div", { class: "btn-row" }, h("button", { class: "btn", type: "button", onclick: (e) => busy(e.currentTarget, async () => { try { await put("/api/account/preferences", { categories: [...sel.categories], requirements: [...sel.requirements], budget_min: lo.input.value, budget_max: hi.input.value }); toast("Preferences saved"); } catch (er) { toastError(er); } }) }, "Save"),
      p.saved ? h("button", { class: "btn btn-ghost", type: "button", onclick: async () => { await del("/api/account/preferences").catch(toastError); toast("Preferences deleted"); preferences(host); } }, "Delete preferences") : null)));
}
async function profile(host) {
  const u = state.user, n = field({ label: "Name", name: "name", value: u.name, required: true }), ph = field({ label: "Mobile (optional)", name: "phone", value: u.phone, inputmode: "tel" });
  const cur = field({ label: "Current password", name: "cur", type: "password", autocomplete: "current-password" }), nw = field({ label: "New password", name: "nw", type: "password", autocomplete: "new-password", hint: "At least 8 characters with a letter and a number." });
  mount(host, h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); await busy(e.submitter, async () => { try { const r = await patch("/api/account/profile", { name: n.input.value, phone: ph.input.value }); state.user = r.user; toast("Profile updated"); } catch (er) { applyFieldErrors({ name: n, phone: ph }, er) || toastError(er); } }); } }, h("h2", { class: "h3" }, "Profile"), h("div", { class: "field" }, h("label", null, "Email"), h("input", { value: u.email, readonly: true })), n, ph, h("button", { class: "btn", type: "submit" }, "Save changes")),
    h("form", { class: "card stack", style: { "margin-top": "18px" }, onsubmit: async (e) => { e.preventDefault(); await busy(e.submitter, async () => { try { const r = await post("/api/auth/password/change", { current_password: cur.input.value, new_password: nw.input.value }); toast(r.message); cur.input.value = nw.input.value = ""; } catch (er) { applyFieldErrors({ current_password: cur, new_password: nw }, er) || toastError(er); } }); } }, h("h2", { class: "h3" }, "Change password"), cur, nw, h("button", { class: "btn btn-ghost", type: "submit" }, "Update password")));
}
async function privacy(host) {
  mount(host, h("div", { class: "card stack" }, h("h2", { class: "h3" }, "Your data"), h("p", { class: "muted" }, "Download everything stored about you, clear what you've saved, or delete your account."),
    h("div", { class: "btn-row" }, h("button", { class: "btn btn-ghost", type: "button", onclick: async () => { try { const d = await get("/api/account/export"); const a = h("a", { href: URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" })), download: "verity-my-data.json" }); document.body.append(a); a.click(); a.remove(); } catch (e) { toastError(e); } } }, "Download my data"),
      h("button", { class: "btn btn-ghost", type: "button", onclick: async () => { await del("/api/account/recent").catch(toastError); toast("Recently viewed cleared"); } }, "Clear recently viewed"),
      h("button", { class: "btn btn-danger", type: "button", onclick: deleteAccount }, "Delete my account"))));
}
function deleteAccount() {
  const pw = field({ label: "Confirm your password", name: "pw", type: "password", autocomplete: "current-password" });
  const d = openDialog({ title: "Delete your account?", body: h("form", { class: "stack", onsubmit: async (e) => { e.preventDefault(); await busy(e.submitter, async () => { try { await del("/api/account", { password: pw.input.value }); d.close(); applySession(await get("/api/auth/me")); toast("Your account was deleted"); refreshCart(); navigate("/"); } catch (er) { applyFieldErrors({ password: pw }, er) || toastError(er); } }); } }, h("p", null, "This removes your profile, wishlist, saved items and preferences. This can't be undone."), pw, h("button", { class: "btn btn-danger", type: "submit" }, "Delete everything")) });
}
async function orders(host) {
  const d = await get("/api/orders");
  mount(host, h("h2", { class: "h3" }, "Your orders"), h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, ["Order", "Date", "Status", "Items", "Total"].map((t) => h("th", null, t)))), h("tbody", null, d.items.map((o) => h("tr", null, h("td", null, o.order_number), h("td", null, fmtDate(o.created_at)), h("td", null, h("span", { class: "badge-s " + statusClass(o.status) }, o.status_label)), h("td", null, o.items.map((i) => i.title).join(", ")), h("td", { class: "r num" }, o.total_text)))))), d.items.some((o) => o.is_demo_seeded) ? notice("demo", "These orders were created by the demo seeder.") : null);
}
