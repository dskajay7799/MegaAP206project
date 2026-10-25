import { boot, state } from "./store.js";
import { start } from "./router.js";
import { buildChrome } from "./chrome.js";
import { initAssistant } from "./assistant.js";
import { h, mount, $ } from "./dom.js";

(async function main() {
  await boot();
  buildChrome();
  initAssistant();
  if (state.offline) {
    $("#banner").prepend(h("div", { class: "demo-banner", role: "alert", style: { background: "#7f1d1d" } }, h("span", null, "Can't reach the Verity server right now. Some things may not load."), h("button", { type: "button", onclick: () => location.reload() }, "Retry")));
  }
  start();
  window.addEventListener("unhandledrejection", (e) => console.error("Unhandled promise rejection:", e.reason));
})();
