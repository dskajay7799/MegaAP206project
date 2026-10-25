import { h, icon, mount } from "../dom.js";
import { post } from "../api.js";
import { state, applySession, refreshCart, guestWish, mergeGuestWishlist } from "../store.js";
import { field, busy, applyFieldErrors, toast, notice } from "../ui.js";
import { navigate } from "../router.js";

const COPY = { login: ["Welcome back", "Sign in"], register: ["Create your account", "Create account"], forgot: ["Reset your password", "Send reset link"], reset: ["Choose a new password", "Update password"] };
export default async function render(ctx) {
  const mode = ctx.mode;
  ctx.title = COPY[mode][1];
  if (state.user && mode !== "reset") { navigate("/account", { replace: true }); return h("div"); }
  const next = ctx.query.get("next") || "/";
  const f = { name: field({ label: "Full name", name: "name", autocomplete: "name", required: true }), email: field({ label: "Email", name: "email", type: "email", autocomplete: "email", required: true, inputmode: "email" }),
    password: field({ label: mode === "reset" ? "New password" : "Password", name: "password", type: "password", autocomplete: mode === "login" ? "current-password" : "new-password", required: true, hint: mode === "login" ? null : "At least 8 characters with a letter and a number." }) };
  const err = h("div", { "aria-live": "assertive" }), out = h("div", { "aria-live": "polite" });
  const fields = { login: [f.email, f.password], register: [f.name, f.email, f.password], forgot: [f.email], reset: [f.password] }[mode];
  const form = h("form", { class: "stack", novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); mount(err); Object.values(f).forEach((x) => x.setError(""));
    const v = (n) => f[n].input.value;
    await busy(e.submitter, async () => {
      try {
        if (mode === "login" || mode === "register") {
          const local = [...guestWish()];
          const s = await post(mode === "login" ? "/api/auth/login" : "/api/auth/register", mode === "login" ? { email: v("email"), password: v("password") } : { name: v("name"), email: v("email"), password: v("password") });
          applySession(s); await mergeGuestWishlist(local); refreshCart();
          toast(mode === "login" ? `Welcome back, ${s.user.name.split(" ")[0]}` : "Account created");
          navigate(next.startsWith("/") ? next : "/");
        } else if (mode === "forgot") {
          const r = await post("/api/auth/password/forgot", { email: v("email") });
          mount(out, notice(r.demo ? "demo" : "ok", h("span", null, r.message, r.demo_reset_link ? [" ", h("a", { href: r.demo_reset_link.replace(/^.*?#/, "#") }, "Open the reset link (demo only)")] : null), "info"));
        } else {
          await post("/api/auth/password/reset", { token: ctx.query.get("token") || "", new_password: v("password") });
          toast("Password updated. Please sign in."); navigate("/login");
        }
      } catch (er) { if (!applyFieldErrors(f, er)) mount(err, h("div", { class: "form-error", role: "alert" }, icon("alert"), er.message)); }
    });
  } }, ...fields, err, h("button", { class: "btn btn-block", type: "submit" }, COPY[mode][1]), out);
  const links = { login: [h("a", { href: "#/forgot" }, "Forgot password?"), h("span", null, "New here? ", h("a", { href: "#/register?next=" + encodeURIComponent(next) }, "Create an account"))], register: [h("span", null, "Already have an account? ", h("a", { href: "#/login?next=" + encodeURIComponent(next) }, "Sign in"))], forgot: [h("a", { href: "#/login" }, "Back to sign in")], reset: [] }[mode];
  return h("div", { class: "wrap section auth" }, h("div", { class: "auth-grid" },
    h("div", { class: "form-card" }, h("h1", { class: "h2" }, COPY[mode][0]), h("div", { style: { margin: "22px 0 8px" } }, form), h("div", { class: "row spread small", style: { "margin-top": "14px" } }, links)),
    h("aside", { class: "auth-side dark" }, h("h2", null, "An account is optional"), h("p", null, "You can browse, search, compare, build a basket, use SmartMatch and ask Verity without signing in."),
      h("ul", { class: "ticks light" }, ["Keep your wishlist across devices", "Save shortlists and comparisons", "Set preferences so SmartMatch starts closer to what you want", "Download or delete your data any time"].map((t) => h("li", null, icon("check"), t))),
      h("p", { class: "small muted" }, "Demo store: nothing you enter here is used for payments. Checkout is disabled."))));
}
