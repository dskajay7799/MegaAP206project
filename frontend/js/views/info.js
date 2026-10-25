import { h, icon } from "../dom.js";
import { get } from "../api.js";
import { state } from "../store.js";
import { errorState, notice } from "../ui.js";

const li = (...t) => h("li", null, ...t);
export default async function render(ctx) {
  const page = ctx.page;
  if (page === "policies") {
    ctx.title = "Delivery, returns & warranty";
    let d; try { d = await get("/api/policies"); } catch (e) { return h("div", { class: "wrap section" }, errorState(e, () => location.reload())); }
    return h("div", { class: "wrap section prose" }, h("h1", null, "Delivery, returns & warranty"), h("p", { class: "muted" }, "This is the exact policy text Verity's assistant cites. Each section has an ID you'll see in answers."),
      d.sections.map((s) => h("section", { class: "card", id: s.id }, h("div", { class: "row spread" }, h("h2", null, s.title), h("code", null, s.id)), h("p", null, s.text))), state.meta?.synthetic_data ? notice("demo", "Demo store policy text, written for this demonstration.") : null);
  }
  if (page === "privacy") {
    ctx.title = "Privacy";
    return h("div", { class: "wrap section prose" }, h("h1", null, "Privacy"), h("p", { class: "muted" }, "What this site actually does with your data."),
      h("section", { class: "card" }, h("h2", null, "Without an account"), h("ul", null, li("Your cart is kept on the server under a random, HttpOnly cookie so it survives a refresh."), li("Your wishlist, compare tray and recently viewed list are kept in your browser as product IDs only."), li("No payment, card, UPI or bank details are asked for anywhere. Checkout is disabled in this demo."))),
      h("section", { class: "card" }, h("h2", null, "Questions you ask Verity"), h("p", null, state.meta?.logging ? "This deployment stores the text of questions, the type of reply, response time and a random per-tab ID to improve answers. No name, email or IP address is attached." : "This deployment does not store your questions."),
        h("p", { class: "muted" }, "Thumbs up/down feedback is only recorded when question logging is on.")),
      h("section", { class: "card" }, h("h2", null, "With an account"), h("ul", null, li("Passwords are hashed with scrypt and never stored or logged in plain text."), li("You can download everything stored about you, clear saved items, or delete your account from Account → Privacy."))));
  }
  if (page === "about") {
    ctx.title = "How Verity works";
    const lens = (t, d) => h("div", { class: "card" }, h("h3", null, t), h("p", { class: "muted" }, d));
    return h("div", { class: "wrap section prose" }, h("h1", null, "How Verity works"), h("p", { class: "lede" }, "Most shopping chatbots confidently invent prices, stock and policies. Verity is built so it can't."),
      h("div", { class: "grid", style: { margin: "28px 0" } }, lens("Grounded answers", "Verity retrieves records from the catalogue and policy, and writes only what those records say. If the data isn't there, it says so."),
        lens("Evidence on every answer", "Each sentence carries a record ID. Open “How I know this” to see the record, the fields used, what was excluded and why."),
        lens("Asks instead of guessing", "If “the blue running shoe” matches three products, Verity asks which one rather than picking a price."),
        lens("Explainable ranking", "SmartMatch scores products by a visible formula over catalogue facts. Missing data counts as unverified, never assumed."),
        lens("Value Lens", "A factor-by-factor view of value from real specs, budget and recorded prices. No invented discounts or histories."),
        lens("AI model optional", state.meta?.llm ? "An AI model rewrites answers, but its text is shown only if every ID, number and stock claim matches the cited record." : "No AI model is connected here. Answers are written directly from records.")),
      h("section", { class: "card" }, h("h2", null, "SmartMatch formula"), h("p", null, h("code", null, "score = Σ(weight × fit) ÷ Σ(weight) × 100")), h("p", { class: "muted" }, "Fit is 0–1 from catalogue facts. If a spec isn't listed, that criterion scores zero and is flagged as unverified.")),
      state.meta?.synthetic_data ? h("section", { class: "card" }, h("h2", null, "About this demo's data"), h("p", null, "Brands, prices, ratings, stock and price history are synthetic. Product images are generated illustrations, not photographs. Checkout is disabled."), h("a", { class: "btn", href: "#/shop" }, "Explore the shop")) : null);
  }
  ctx.title = "Page not found";
  return h("div", { class: "wrap section" }, h("div", { class: "state" }, icon("search"), h("h1", { class: "h2" }, "Page not found"), h("p", null, "That page doesn't exist."), h("a", { class: "btn", href: "#/" }, "Go home")));
}
