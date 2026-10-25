import { h, icon, mount, debounce } from "../dom.js";
import { post } from "../api.js";
import { state } from "../store.js";
import { img, productAlt, productCard, toast, errorState, notice, addToCart, busy, emptyState } from "../ui.js";
import { setQuery } from "../router.js";

const EX = ["wireless headphones for studying, commuting and long battery life, under ₹3,000", "running shoes under 2500", "backpack for laptop and travel under 2500", "vacuum insulated bottle for the gym"];
export default async function render(ctx) {
  ctx.title = "SmartMatch";
  const text = h("textarea", { class: "input", rows: 3, maxlength: 500, "aria-label": "Describe what you need", placeholder: "e.g. wireless headphones for studying and commuting, long battery, under ₹3,000" }, ctx.query.get("q") || "");
  const budget = h("input", { class: "input", type: "number", min: 0, inputmode: "numeric", placeholder: "Budget ₹ (optional)", "aria-label": "Budget in rupees" });
  const stock = h("input", { type: "checkbox", checked: true }), prefs = h("input", { type: "checkbox", checked: true });
  const out = h("div", { "aria-live": "polite" });
  let weights = {};
  async function run(reset = true) {
    if (!text.value.trim()) return mount(out, notice("warn", "Describe what you need first.", "alert"));
    if (reset) weights = {};
    mount(out, h("div", { class: "sk", style: { height: "260px" } }));
    try { paint(await post("/api/smartmatch", { text: text.value, budget: budget.value || null, weights, in_stock_only: stock.checked, use_preferences: prefs.checked })); }
    catch (e) { mount(out, errorState(e, () => run(false))); }
  }
  const again = debounce(() => run(false), 350);
  function addText(s) { text.value = (text.value.trim() + " " + s).trim(); run(); }
  function matchCard(m) {
    const p = m.product, bars = m.breakdown.filter((b) => b.max_points > 0);
    return h("article", { class: "match card" }, h("div", { class: "m-top" }, h("div", { class: "rank" }, "#" + m.rank), h("a", { href: `#/product/${encodeURIComponent(p.id)}`, class: "m-img" }, img(p.image, productAlt(p))),
      h("div", { class: "grow" }, h("div", { class: "pbrand" }, p.brand), h("a", { class: "ptitle", href: `#/product/${encodeURIComponent(p.id)}` }, p.title), h("div", { class: "row small" }, h("b", { class: "num" }, p.price_text), h("span", { class: "muted" }, p.stock_text), m.price_vs_budget ? h("span", { class: "vd good" }, m.price_vs_budget) : null)),
      h("div", { class: "scorebox" }, h("div", { class: "ring", style: { "--p": m.score ?? 0 }, role: "img", "aria-label": `Match score ${m.score} out of 100` }, h("b", null, Math.round(m.score ?? 0))), h("small", { class: "muted" }, `${Math.round((m.coverage ?? 0) * 100)}% verified`))),
      h("div", { class: "seg", role: "img", "aria-label": "Score breakdown by criterion" }, bars.map((b, i) => h("i", { style: { "--w": b.points + "%", "--c": ["#2540ff", "#0b1026", "#a9d93d", "#e8604c", "#6b4de6", "#1b8a8a", "#f4b400"][i % 7] }, title: `${b.label}: ${b.points} pts` }))),
      h("ul", { class: "brk" }, m.breakdown.map((b, i) => h("li", null, h("span", { class: "vd " + b.verdict }, b.verdict), h("span", { class: "grow" }, h("b", null, b.label), h("small", { class: "muted" }, b.detail)), h("span", { class: "num small" }, b.weight > 0 ? `${b.points}/${b.max_points}` : "")))),
      m.missing.length ? h("p", { class: "small", style: { color: "var(--warn)" } }, icon("alert"), " Not listed, so not assumed: ", m.missing.join("; ")) : null,
      h("div", { class: "btn-row" }, h("a", { class: "btn btn-sm btn-ghost", href: `#/product/${encodeURIComponent(p.id)}` }, "View"), !p.has_variants && p.stock === "in_stock" ? h("button", { class: "btn btn-sm", type: "button", onclick: (e) => busy(e.currentTarget, () => addToCart(p).catch(() => {})) }, "Add to cart") : null));
  }
  function paint(r) {
    if (r.status === "clarify") return mount(out, h("div", { class: "card clar" }, icon("info"), h("h2", { class: "h3" }, r.clarify.question), h("p", { class: "muted" }, r.clarify.reason), h("div", { class: "chips" }, r.clarify.options.map((o) => h("button", { class: "chip", type: "button", onclick: () => addText(o.append) }, o.label)))));
    const intent = h("div", { class: "chips" }, r.budget_text ? h("span", { class: "chip static" }, "Budget " + r.budget_text) : null, r.intent.product_words.map((w) => h("span", { class: "chip static" }, w)), r.criteria.map((c) => h("span", { class: "chip static chip-x" }, c.label)));
    const pri = r.criteria.length ? h("div", { class: "card" }, h("h2", { class: "h3" }, "Your priorities"), h("p", { class: "muted small" }, "Move a slider and the ranking recalculates. 0 ignores that factor."), h("div", { class: "sliders" }, r.criteria.map((c) => h("label", { class: "slider" }, h("span", null, c.label, c.source === "preference" ? h("small", { class: "muted" }, " (from your preferences)") : null), h("input", { type: "range", min: 0, max: 5, step: 1, value: c.weight, "aria-label": `Importance of ${c.label}`, oninput: (e) => { weights[c.id] = +e.target.value; e.target.nextSibling.textContent = e.target.value; again(); } }), h("output", null, c.weight))))) : null;
    mount(out, h("div", { class: "sm-head" }, intent, r.applied_preferences.length ? notice("info", "Using " + r.applied_preferences.join(", ") + ". Untick “use my preferences” to ignore.") : null),
      r.status === "no_match" ? h("div", { style: { margin: "16px 0" } }, emptyState({ ic: "search", title: "No match in the catalogue", text: r.notes.join(" ") || "Nothing fits those criteria." })) : null,
      r.matches.length ? h("div", { class: "sm-grid" }, h("div", { class: "stack", style: { "--gap": "16px" } }, r.matches.map(matchCard)), h("div", { class: "stack side", style: { "--gap": "16px" } }, pri,
        r.excluded.length ? h("div", { class: "card" }, h("h2", { class: "h3" }, "Left out, and why"), h("ul", { class: "plain small" }, r.excluded.map((e) => h("li", null, h("a", { href: `#/product/${encodeURIComponent(e.id)}` }, e.title), ": ", e.reason)))) : null,
        r.notes.length ? h("div", { class: "card" }, h("h2", { class: "h3" }, "Things to know"), h("ul", { class: "plain small" }, r.notes.map((n) => h("li", null, n)))) : null,
        r.follow_up ? h("div", { class: "card" }, h("p", null, r.follow_up.question), h("div", { class: "chips" }, r.follow_up.chips.map((c) => h("span", { class: "chip static" }, c.label)))) : null,
        h("details", { class: "disc" }, h("summary", null, "How is the score calculated?"), h("div", null, h("code", null, r.formula), h("p", { class: "small muted" }, "No AI model is involved in the score, so the same question always gives the same ranking."))))) : null);
  }
  const form = h("form", { class: "card sm-form", onsubmit: (e) => { e.preventDefault(); setQuery({ q: text.value.trim().slice(0, 200) }); run(); } },
    h("label", { class: "label", for: "sm-text" }, "Describe what you need"), (text.id = "sm-text", text), h("div", { class: "row spread" }, h("div", { class: "row" }, budget, h("label", { class: "check" }, stock, "In stock only"), state.user ? h("label", { class: "check" }, prefs, "Use my preferences") : null), h("button", { class: "btn", type: "submit" }, icon("spark"), "Match me")),
    h("div", { class: "chips" }, EX.map((x) => h("button", { class: "chip", type: "button", onclick: () => { text.value = x; run(); } }, x.length > 52 ? x.slice(0, 50) + "…" : x))));
  if (text.value) run();
  return h("div", { class: "wrap section" }, h("div", { class: "section-head" }, h("div", null, h("h1", { class: "h2" }, "SmartMatch"), h("p", null, "Say what you need. Verity ranks products by a visible formula over real catalogue facts, and flags anything it can't verify."))), form, h("div", { style: { "margin-top": "22px" } }, out));
}
