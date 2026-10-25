// The Ask Verity panel. It renders the assistant's response schema exactly as the backend defines it (see README "Assistant response schema"):
//   message + [ID] citations, products[], options[] (choices), followups[] (suggestions + actions), comparison{columns,rows}, citations[], evidence{}
import { h, icon, mount, $, add, clear } from "./dom.js";
import { state, setCompare, inCompare, toggleCompare } from "./store.js";
import { post, get } from "./api.js";
import { navigate } from "./router.js";
import { openDialog, toast, toastError, img, productAlt, addToCart, busy } from "./ui.js";

const sid = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random())).replace(/-/g, "").slice(0, 12);
const chat = { messages: [], product: null, pending: false, status: null, dlg: null, log: null, input: null };

export function initAssistant() {
  get("/api/ai/status").then((s) => { chat.status = s; }).catch(() => {});
}

export function openAssistant({ prompt, product } = {}) {
  if (product) chat.product = { id: product.id, title: product.title };
  if (chat.dlg) { if (prompt) send(prompt); return; }
  chat.log = h("div", { class: "chat-log", role: "log", "aria-live": "polite", "aria-label": "Conversation with Verity" });
  chat.input = h("input", { name: "q", type: "text", maxlength: state.meta?.max_message_chars || 500, autocomplete: "off", placeholder: chat.product ? "Ask about this product…" : "Ask about products or policies…", "aria-label": "Your question" });
  const ctxChip = h("div", { class: "ctx-chip", hidden: !chat.product });
  const paintChip = () => { ctxChip.hidden = !chat.product; mount(ctxChip, chat.product ? [icon("tag"), h("span", null, "About: ", h("b", null, chat.product.title)), h("button", { type: "button", "aria-label": "Stop asking about this product", onclick: () => { chat.product = null; paintChip(); chat.input.placeholder = "Ask about products or policies…"; welcome(); } }, icon("x"))] : []); };
  const form = h("form", { class: "composer-bar", onsubmit: (e) => { e.preventDefault(); const t = chat.input.value.trim(); if (t) { chat.input.value = ""; send(t); } } },
    chat.input, h("button", { class: "btn btn-sm", type: "submit", "aria-label": "Send" }, icon("arrow")));
  const foot = h("div", { class: "chat-foot" }, ctxChip, form);
  chat.dlg = openDialog({ title: "Ask Verity", side: true, cls: "assistant-sheet", body: [statusLine(), chat.log], footer: foot, onClose: () => { chat.dlg = null; chat.log = null; } });
  chat.dlg.sheet.querySelector(".sheet-f").classList.add("chat-sheet-f");
  paintChip();
  chat.messages.length ? chat.messages.forEach((m) => draw(m, false)) : welcome();
  scroll(true);
  chat.input.focus();
  if (prompt) send(prompt);
}

function statusLine() {
  const el = h("p", { class: "ai-status small" });
  const paint = (s) => mount(el, s?.llm_configured ? [icon("shield"), "AI wording is on. Each answer is checked against the records it cites; if a check fails you see the plain grounded text."]
    : [icon("shield"), "Grounded mode: every answer is written straight from catalogue and policy records. No AI model is connected."]);
  paint(chat.status);
  if (!chat.status) get("/api/ai/status").then((s) => { chat.status = s; paint(s); }).catch(() => {});
  return el;
}

function welcome() {
  if (!chat.log || chat.messages.length) return;
  const cats = (state.meta?.categories || []).slice(0, 2).map((c) => c.name);
  const prompts = chat.product
    ? [["What are the specs?", `specs of ${chat.product.id}`], ["Is it in stock?", `is ${chat.product.id} in stock?`], ["What colours does it come in?", "what colours does it come in"], ["Is it covered by warranty?", "what about its warranty"]]
    : [["Something to carry my laptop", "something to carry my laptop"], ["Headphones with the longest battery", "which headphones have the longest battery"],
       ["Can I return a shirt after 10 days?", "can I return a shirt after 10 days"], ["Headphones under ₹3,000", "headphones under 3000"], ["Is shipping free?", "is shipping free?"],
       ...cats.slice(0, 1).map((c) => [`Show me ${c}`, `show me ${c}`])];
  clear(chat.log);
  chat.log.append(h("div", { class: "welcome" }, h("h3", null, chat.product ? "Ask about this product" : "What are you shopping for?"),
    h("p", { class: "muted" }, "I answer only from the catalogue and the store policy, and I show the record behind every answer. If I don't know, I'll say so."),
    h("div", { class: "chips" }, prompts.map(([label, q]) => h("button", { class: "chip", type: "button", onclick: () => send(q) }, label)))));
}

function scroll(force) {
  const body = chat.log?.closest(".sheet-b");
  if (body) body.scrollTo({ top: body.scrollHeight, behavior: force ? "auto" : "smooth" });
}

async function send(text) {
  if (chat.pending || !chat.log) return;
  if (!chat.messages.length) clear(chat.log);
  const wire = chat.product && !/\bVRT-|[A-Z]{2,5}-\d+/.test(text) ? `${text} ${chat.product.id}` : text;         // keep the product in context for follow-ups
  const history = chat.messages.filter((m) => m.role === "user").slice(-6).map((m) => ({ role: "user", content: m.wire }));
  const um = { role: "user", text, wire };
  chat.messages.push(um); draw(um);
  chat.pending = true;
  const typing = h("div", { class: "msg bot" }, h("div", { class: "bubble typing", "aria-label": "Verity is looking this up", role: "status" }, h("i"), h("i"), h("i")));
  chat.log.append(typing); scroll();
  try {
    const res = await post("/api/chat", { message: wire, history, session_id: sid }, { timeout: 25000 });
    typing.remove();
    const bm = { role: "bot", res }; chat.messages.push(bm); draw(bm);
  } catch (e) {
    typing.remove();
    const bm = { role: "bot", error: e.message || "Something went wrong.", retry: text }; chat.messages.push(bm); draw(bm);
  } finally { chat.pending = false; scroll(); chat.input?.focus(); }
}

function draw(m, animate = true) {
  if (!chat.log) return;
  chat.log.append(m.role === "user" ? h("div", { class: "msg user" }, h("div", { class: "bubble" }, m.text)) : m.error ? errorBubble(m) : botBubble(m));
}
const errorBubble = (m) => h("div", { class: "msg bot" }, h("div", { class: "bubble bad", role: "alert" }, h("p", null, m.error), h("button", { class: "btn btn-sm btn-ghost", type: "button", onclick: (e) => { e.target.closest(".msg").remove(); chat.messages.pop(); chat.messages.pop(); send(m.retry); } }, "Try again")));

/* ---------- a full assistant reply ---------- */
function botBubble(m) {
  const res = m.res, ids = new Set(res.citations.map((c) => c.id));
  const evidence = evidencePanel(res);
  const body = h("div", { class: "bubble " + res.status }, h("p", { class: "answer" }, withCites(res.message, ids, evidence)));
  const wrap = h("div", { class: "msg bot" }, body);
  if (res.status === "clarify" && res.options.length) body.append(h("div", { class: "choices", role: "group", "aria-label": "Choose one" }, res.options.map((o) => choice(o, res))));
  else if (res.products.length) body.append(h("div", { class: "minis" }, res.products.slice(0, 4).map(mini)));
  if (res.comparison) body.append(comparisonTable(res.comparison));
  if (res.followups.length) body.append(h("div", { class: "fu" }, res.followups.map((o) => followup(o, res))));
  if (res.citations.length || res.evidence?.excluded?.length || res.evidence?.reason || res.evidence?.missing?.length) body.append(evidence);
  body.append(meta(res));
  return wrap;
}

function withCites(text, ids, evidence) {
  const out = [];
  let last = 0;
  for (const mt of text.matchAll(/\[([A-Za-z0-9_.-]+)\]/g)) {
    if (!ids.has(mt[1])) continue;
    out.push(text.slice(last, mt.index));
    out.push(h("button", { class: "cite", type: "button", title: "Show the record behind this", onclick: () => openSource(evidence, mt[1]) }, mt[1]));
    last = mt.index + mt[0].length;
  }
  out.push(text.slice(last));
  return out;
}
function openSource(evidence, id) {
  evidence.open = true;
  const item = evidence.querySelector(`[data-src="${CSS.escape(id)}"]`);
  if (item) { item.classList.add("flash"); item.scrollIntoView({ block: "nearest", behavior: "smooth" }); item.querySelector("a,button")?.focus({ preventScroll: true }); setTimeout(() => item.classList.remove("flash"), 1600); }
}

/* option → choice card (type "choice": pick one to continue) */
function choice(o, res) {
  const p = res.products.find((x) => x.id === o.product_ids[0]);
  return h("button", { class: "choice", type: "button", onclick: () => send(o.query) }, p ? img(p.image, productAlt(p)) : null,
    h("span", { class: "grow" }, h("b", null, o.label), h("small", { class: "muted" }, o.detail || "")), icon("chevR"));
}

/* products[] → recommended product mini cards */
function mini(p) {
  const actions = [h("a", { class: "btn btn-sm btn-ghost", href: `#/product/${encodeURIComponent(p.id)}`, onclick: close }, "View")];
  if (p.stock === "in_stock") actions.push(p.has_variants ? h("a", { class: "btn btn-sm btn-ink", href: `#/product/${encodeURIComponent(p.id)}`, onclick: close }, "Options")
    : h("button", { class: "btn btn-sm", type: "button", onclick: (e) => busy(e.currentTarget, () => addToCart(p).catch(() => {})) }, "Add"));
  const cmp = h("button", { class: "btn btn-sm btn-ghost", type: "button", "data-cmp": p.id, "aria-pressed": String(inCompare(p.id)), onclick: () => { if (!toggleCompare(p.id)) toast("You can compare up to 4 products.", { kind: "bad" }); } }, icon("compare"), "Compare");
  return h("div", { class: "mini" }, h("a", { href: `#/product/${encodeURIComponent(p.id)}`, onclick: close, tabindex: "-1", "aria-hidden": "true" }, img(p.image, productAlt(p))),
    h("div", { class: "grow" }, h("a", { class: "t", href: `#/product/${encodeURIComponent(p.id)}`, onclick: close }, p.title), h("div", { class: "row small" }, h("b", { class: "num" }, p.price_text), h("span", { class: "muted" }, p.stock_text)),
      h("div", { class: "btn-row" }, actions, cmp)));
}
const close = () => chat.dlg && chat.dlg.close();

/* followups[] → suggestion chips and action buttons */
function followup(o, res) {
  if (o.type === "suggestion") return h("button", { class: "chip", type: "button", onclick: () => send(o.query) }, o.label);
  const go = () => {
    const ids = o.product_ids;
    if (o.action === "view_product") { close(); navigate(`/product/${encodeURIComponent(ids[0])}`); }
    else if (o.action === "compare") { setCompare(ids); close(); navigate(`/compare?ids=${ids.map(encodeURIComponent).join(",")}`); }
    else if (o.action === "add_to_cart") {
      const p = res.products.find((x) => x.id === ids[0]);
      if (!p || p.has_variants) { close(); navigate(`/product/${encodeURIComponent(ids[0])}`); toast("Choose a size or colour first", { ms: 2500 }); }
      else addToCart(p).catch(() => {});
    }
  };
  return h("button", { class: "chip action", type: "button", onclick: go }, icon(o.action === "compare" ? "compare" : o.action === "add_to_cart" ? "cart" : "eye"), o.label);
}

/* comparison{columns,rows} → table */
export function comparisonTable(cmp) {
  const head = h("tr", null, h("th", { scope: "col" }, ""), cmp.columns.map((c) => h("th", { scope: "col" }, h("a", { href: c.url, onclick: close }, img(c.image, `Illustration of ${c.title}`), h("span", null, c.title)), h("b", { class: "num" }, c.price_text))));
  const groups = { overview: "Overview", features: "Features", details: "Details" };
  const rows = [];
  for (const g of Object.keys(groups)) {
    const rs = cmp.rows.filter((r) => r.group === g && !(g === "overview" && r.key === "price"));
    if (!rs.length) continue;
    rows.push(h("tr", { class: "grp" }, h("th", { colspan: cmp.columns.length + 1 }, groups[g])));
    rs.forEach((r) => rows.push(h("tr", { class: r.differs ? "diff" : "" }, h("th", { scope: "row" }, r.label), r.values.map((v) => h("td", { class: v === "Not available in catalogue" ? "na" : "" }, v)))));
  }
  return h("div", { class: "table-wrap cmp-mini" }, h("table", null, h("caption", { class: "sr-only" }, "Product comparison"), h("thead", null, head), h("tbody", null, rows)));
}

/* citations[] + evidence{} → "How I know this" */
function evidencePanel(res) {
  const ev = res.evidence || {};
  const sections = [];
  if (res.citations.length) sections.push(h("div", null, h("h4", null, "Sources used"), h("ul", { class: "srcs" }, res.citations.map((c) => h("li", { "data-src": c.id },
    h("div", { class: "row spread" }, h("span", null, h("span", { class: "badge-s " + (c.kind === "policy" ? "new" : "") }, c.source), " ", h("b", null, c.label)), h("a", { class: "small", href: c.url, onclick: close }, c.kind === "policy" ? "Read policy" : "Open product")),
    h("div", { class: "small muted" }, h("code", null, c.id), " · ", c.snippet),
    c.fields.length ? h("div", { class: "row" }, h("span", { class: "small muted" }, "Used from this record:"), c.fields.map((f) => h("span", { class: "chip static", style: { "min-height": "28px", padding: "0 10px", "font-size": ".78rem" } }, f))) : null,
    c.kind === "policy" ? h("blockquote", null, c.record.text) : null)))));
  if (ev.reason) sections.push(h("div", null, h("h4", null, "Why these results"), h("p", { class: "small" }, ev.reason)));
  if (ev.excluded?.length) sections.push(h("div", null, h("h4", null, "Left out, and why"), h("ul", { class: "small plain" }, ev.excluded.map((x) => h("li", null, h("a", { href: `#/product/${encodeURIComponent(x.id)}`, onclick: close }, x.title), ": ", x.reason)))));
  if (ev.missing?.length) sections.push(h("div", null, h("h4", null, "Not in the record"), h("ul", { class: "small plain" }, ev.missing.map((x) => h("li", null, x)))));
  return h("details", { class: "disc evidence" }, h("summary", null, icon("shield"), "How I know this"), h("div", { class: "stack", style: { "--gap": "14px" } }, sections));
}

/* metrics + feedback + save */
function meta(res) {
  const m = res.metrics || {}, row = h("div", { class: "meta-row small muted" });
  row.append(h("span", null, res.mode === "ai" ? "AI wording, verified" : "Grounded text", " · ", Math.round(m.latency_ms ?? 0), " ms", m.llm_tokens ? ` · ${m.llm_tokens} tokens` : ""));
  const fb = h("span", { class: "fb" });
  const vote = (helpful) => post("/api/feedback", { helpful, request_id: m.request_id || "", session_id: sid }).then(() => mount(fb, "Thanks for the feedback"), toastError);
  mount(fb, h("button", { type: "button", "aria-label": "Helpful", title: "Helpful", onclick: () => vote(true) }, "👍"), h("button", { type: "button", "aria-label": "Not helpful", title: "Not helpful", onclick: () => vote(false) }, "👎"));
  row.append(fb);
  if (state.user && res.products.length && res.status === "answer") row.append(h("button", { class: "linklike small", type: "button", onclick: async (e) => {
    const msgs = chat.messages.filter((x) => x.res || x.role === "user").slice(-4).map((x) => ({ role: x.role === "user" ? "user" : "assistant", text: x.text || x.res.message }));
    try { await post("/api/account/chats", { messages: msgs, product_ids: res.products.map((p) => p.id) }); toast("Shortlist saved to your account"); e.target.remove(); } catch (er) { toastError(er); } } }, "Save shortlist"));
  return row;
}
