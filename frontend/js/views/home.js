import { h, icon, mount, qs } from "../dom.js";
import { get, post } from "../api.js";
import { state } from "../store.js";
import { productCard, img, productAlt, errorState, skeletonGrid } from "../ui.js";
import { openAssistant } from "../assistant.js";
import { navigate } from "../router.js";

const EXAMPLE = "wireless headphones for studying under ₹3,000";
const reduced = matchMedia("(prefers-reduced-motion: reduce)"), fine = matchMedia("(hover: hover) and (pointer: fine)");

function rail(title, sub, products, linkTo, note) {
  if (!products.length) return null;
  return h("section", { class: "section wrap", "aria-label": title }, h("div", { class: "section-head" }, h("div", null, h("h2", null, title), sub ? h("p", null, sub) : null), linkTo ? h("a", { class: "link-arrow", href: "#" + linkTo }, "See all", icon("arrow")) : null),
    h("div", { class: "grid g4" }, products.slice(0, 4).map(productCard)), note ? h("p", { class: "muted small", style: { "margin-top": "12px" } }, note) : null);
}

function hero(featured) {
  const input = h("input", { name: "need", type: "text", "aria-label": "Describe what you need", placeholder: "Describe what you need, e.g. “a laptop backpack for commuting under ₹2,500”", maxlength: 300 });
  const go = (t) => navigate("/smartmatch" + qs({ q: t }));
  const plates = featured.filter((p) => p.image).slice(0, 4);
  const chip = h("a", { class: "match-chip", href: "#/smartmatch" + qs({ q: EXAMPLE }), hidden: true, "aria-label": "See this SmartMatch example" });
  post("/api/smartmatch", { text: EXAMPLE }).then((r) => {
    const m = r.matches[0]; if (!m) return;
    mount(chip, h("span", { class: "ring", style: { "--p": "0" } }, h("b", null, Math.round(m.score))), h("span", null, h("b", null, m.product.title), h("small", null, `Top match for “${EXAMPLE}” · scored from ${m.breakdown.length} criteria`)));
    chip.hidden = false; requestAnimationFrame(() => requestAnimationFrame(() => chip.querySelector(".ring").style.setProperty("--p", String(m.score))));
  }).catch(() => {});
  const stage = h("div", { class: "stage", "aria-hidden": plates.length ? null : "true" }, h("div", { class: "grid3d" }), h("div", { class: "deco-ring" }), h("div", { class: "deco-cube" }, ...Array.from({ length: 6 }, () => h("i"))),
    plates.map((p, i) => h("a", { class: `plate p${i + 1}`, href: `#/product/${encodeURIComponent(p.id)}`, tabindex: i ? "-1" : "0", "aria-label": `${p.title}, ${p.price_text}` }, img(p.image, "", { eager: true }), h("span", { class: "cap" }, h("span", null, p.title.split(" ").slice(0, 3).join(" ")), h("b", null, p.price_text)))), chip);
  const wrap = h("div", { class: "stage-wrap" }, stage);
  if (fine.matches && !reduced.matches) wrap.addEventListener("pointermove", (e) => { const r = wrap.getBoundingClientRect(); stage.style.setProperty("--rx", (((e.clientX - r.left) / r.width - .5) * 16).toFixed(2)); stage.style.setProperty("--ry", ((.5 - (e.clientY - r.top) / r.height) * 12).toFixed(2)); });
  if (fine.matches) wrap.addEventListener("pointerleave", () => { stage.style.setProperty("--rx", 0); stage.style.setProperty("--ry", 0); });
  return h("section", { class: "hero wrap" }, h("div", { class: "hero-grid" },
    h("div", null, h("h1", null, "Shop by what you ", h("span", { class: "hl" }, "need"), ". See the proof."),
      h("p", { class: "lede" }, "Verity matches products to your budget and priorities, explains every score, and shows the catalogue record behind each answer. It never invents a price, a spec or a policy."),
      h("form", { class: "composer", onsubmit: (e) => { e.preventDefault(); const t = input.value.trim(); go(t || EXAMPLE); } }, input, h("button", { class: "btn btn-ink", type: "submit" }, icon("spark"), "Match me")),
      h("div", { class: "chips" }, ["headphones for studying under 3000", "backpack for commuting", "running shoes", "vacuum bottle for travel"].map((t) => h("button", { class: "chip", type: "button", onclick: () => go(t) }, t)),
        h("button", { class: "chip", type: "button", onclick: () => openAssistant({}) }, icon("spark"), "Or just ask Verity")),
      h("div", { class: "proof" }, ["Every answer cites its source", "No invented prices or stock", "Scores you can inspect"].map((t) => h("span", null, icon("check"), t)))), wrap));
}

function categories(cats) {
  return h("section", { class: "wrap", "aria-label": "Shop by category" }, h("div", { class: "cat-rail" }, cats.map((c) => h("a", { class: "cat", href: "#/shop" + qs({ category: c.name }) }, c.image ? img(c.image, "") : null, h("span", null, h("b", null, c.name), h("small", null, `${c.count} products`))))));
}

function collections(cols) {
  if (!cols.length) return null;
  let active = 0;
  const body = h("div", { class: "grid g4" });
  const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": "Collections" });
  const paint = () => {
    mount(tabs, cols.map((c, i) => h("button", { role: "tab", "aria-selected": String(i === active), id: "col-" + i, onclick: () => { active = i; paint(); } }, c.title)));
    mount(body, cols[active].products.map(productCard));
    body.setAttribute("role", "tabpanel"); body.setAttribute("aria-labelledby", "col-" + active);
  };
  paint();
  return h("section", { class: "section wrap", "aria-label": "Collections" }, h("div", { class: "section-head" }, h("div", null, h("h2", null, "Collections built from real uses"), h("p", null, "Each product lists the uses it suits in the catalogue. These groups are made from that data, not from guesses."))),
    tabs, h("div", { style: { "margin-top": "22px" } }, body), h("p", { style: { "margin-top": "14px" } }, h("a", { class: "link-arrow", href: "#/shop" }, "Browse everything", icon("arrow"))));
}

async function valueSpotlight(featured) {
  const p = featured.find((x) => x.stock === "in_stock" && x.category === "Electronics") || featured[0];
  if (!p) return null;
  let d; try { d = await get(`/api/products/${encodeURIComponent(p.id)}/value-lens?budget=3000&need=${encodeURIComponent("long battery life")}`); } catch { return null; }
  return h("section", { class: "wrap" }, h("div", { class: "spot dark" }, h("div", null, h("h2", null, "Value, explained"), h("p", { class: "muted", style: { "margin-top": "12px", "max-width": "46ch" } }, "Verity doesn't call the cheapest thing the best. It lines up what the catalogue says about a product against your budget, your must-haves and its peers, and tells you what it couldn't check."),
    h("div", { class: "btn-row", style: { "margin-top": "20px" } }, h("a", { class: "btn btn-lime", href: "#/smartmatch" }, icon("spark"), "Try SmartMatch"), h("a", { class: "btn btn-ghost", href: "#/compare" }, "Open compare studio"))),
    h("div", { class: "lens-card" }, h("div", { class: "row spread" }, h("b", null, p.title), h("span", { class: "badge-s new" }, "Example")), h("p", { class: "small muted" }, "Budget ₹3,000, wants long battery life"),
      h("ul", { class: "factors" }, d.factors.slice(0, 5).map((f) => h("li", null, h("span", { class: "vd " + f.verdict }, f.verdict), h("span", null, h("b", null, f.label), h("small", { class: "muted" }, f.detail))))), h("p", { class: "small muted" }, d.summary))));
}

function why() {
  const items = [["shield", "Grounded, or silent", "Answers come only from catalogue and policy records. When the data isn't there, Verity says so instead of guessing."], ["eye", "Evidence on every answer", "Open “How I know this” to see the exact record, the fields used, what was left out and what's missing."], ["chart", "Scores you can audit", "SmartMatch shows each criterion, its weight and the catalogue fact behind it. Change the weights and watch the ranking move."]];
  return h("section", { class: "section wrap", "aria-label": "Why Verity is different" }, h("div", { class: "section-head" }, h("h2", null, "Why Verity is different")), h("div", { class: "why" }, items.map(([ic, t, p]) => h("div", { class: "card" }, icon(ic), h("h3", null, t), h("p", { class: "muted" }, p)))), h("p", { style: { "margin-top": "16px" } }, h("a", { class: "link-arrow", href: "#/about" }, "How Verity works", icon("arrow"))));
}

async function personal() {
  if (!state.user) return h("section", { class: "wrap" }, h("div", { class: "card row spread" }, h("div", null, h("h3", null, "Get picks that fit you"), h("p", { class: "muted" }, "Sign in and save a few optional preferences. Verity uses them for search defaults and SmartMatch, and you can delete them any time.")), h("a", { class: "btn btn-ghost", href: "#/login" }, "Sign in")));
  let r; try { r = await get("/api/recommendations?limit=4"); } catch { return null; }
  if (r.items.length) return h("section", { class: "section wrap", "aria-label": "Picked for you" }, h("div", { class: "section-head" }, h("div", null, h("h2", null, "Picked for you"), h("p", null, "Based on " + r.basis.join(" and ") + "."))), h("div", { class: "grid g4" }, r.items.map((i) => h("div", null, productCard(i.product), h("p", { class: "small muted", style: { "margin-top": "8px" } }, i.reasons[0])))));
  return h("section", { class: "wrap" }, h("div", { class: "card row spread" }, h("div", null, h("h3", null, "Tell Verity what you like"), h("p", { class: "muted" }, r.reason)), h("a", { class: "btn btn-ghost", href: "#/account/preferences" }, "Set preferences")));
}

export default async function render(ctx) {
  ctx.title = "Shop by what you need";
  const root = h("div", null);
  let d;
  try { d = await get("/api/home"); } catch (e) { return h("div", { class: "wrap section" }, errorState(e, () => navigate("/", { replace: true }))); }
  root.append(hero(d.featured), categories(d.categories), rail("Featured", "Hand-picked from the catalogue.", d.featured, "/shop?featured=1"), rail("New arrivals", "Added to the catalogue in the last 30 days.", d.new_arrivals, "/shop?sort=newest"),
    d.trending.length ? rail("Trending", d.trending_basis, d.trending, "/shop") : null);
  const slots = [h("div", null), h("div", null)];
  root.append(slots[0], collections(d.collections));
  const [pv, lens] = await Promise.allSettled([personal(), valueSpotlight(d.featured)]);
  if (pv.value) slots[0].append(pv.value);
  root.append(h("div", { class: "section" }, lens.value || null), why());
  return root;
}
