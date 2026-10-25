import { h, icon, mount } from "../dom.js";
import { get } from "../api.js";
import { state, on } from "../store.js";
import { productCard, emptyState, errorState, skeletonGrid, notice } from "../ui.js";

export default async function render(ctx) {
  ctx.title = "Wishlist";
  const host = h("div");
  async function load() {
    const ids = [...state.wishlist].slice(0, 24);
    if (!ids.length) return mount(host, emptyState({ ic: "heart", title: "Nothing saved yet", text: "Tap the heart on any product to keep it here.", actions: [h("a", { class: "btn", href: "#/shop" }, "Browse the shop")] }));
    mount(host, skeletonGrid(4));
    try { const d = await get("/api/products?page_size=24&ids=" + ids.map(encodeURIComponent).join(",")); mount(host, h("div", { class: "grid" }, d.items.map(productCard))); } catch (e) { mount(host, errorState(e, load)); }
  }
  const off = on("wishlist", () => { if (host.isConnected) load(); });
  load();
  return { node: h("div", { class: "wrap section" }, h("h1", null, "Wishlist"), state.user ? null : h("div", { style: { margin: "16px 0" } }, notice("info", h("span", null, "Saved on this device. ", h("a", { href: "#/login?next=%2Fwishlist" }, "Sign in"), " to keep your wishlist across devices."))), h("div", { style: { "margin-top": "22px" } }, host)), destroy: off };
}
