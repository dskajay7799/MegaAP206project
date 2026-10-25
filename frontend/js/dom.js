// Tiny DOM toolkit. Dynamic data only ever enters the page as text nodes or attributes (never innerHTML), which keeps the strict CSP meaningful.
const SVG_NS = "http://www.w3.org/2000/svg";
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  add(el, kids);
  return el;
}
export function add(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return el;
}
export function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  add(el, kids);
  return el;
}
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const mount = (el, ...kids) => add(clear(el), kids);

const ICONS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>', cart: '<path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.4a2 2 0 0 0 2-1.5L20.5 8H6"/><circle cx="10" cy="20.5" r="1.3"/><circle cx="17" cy="20.5" r="1.3"/>',
  heart: '<path d="M12 20.5s-7.5-4.6-9.2-9.4C1.6 7.5 3.8 4.5 7 4.5c2 0 3.7 1.1 5 3 1.3-1.9 3-3 5-3 3.200 0 5.400 3 4.200 6.600-1.700 4.800-9.200 9.400-9.200 9.400Z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c.6-4 3.700-6.500 8-6.500s7.400 2.500 8 6.500"/>', menu: '<path d="M4 7h16M4 12h16M4 17h16"/>', x: '<path d="m6 6 12 12M18 6 6 18"/>',
  check: '<path d="m5 12.500 4.500 4.500L19 7.500"/>', alert: '<path d="M12 3.500 2.500 20h19L12 3.500Z"/><path d="M12 10v4.500M12 17.500v.1"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.500M12 7.500v.1"/>',
  spark: '<path d="M12 3c.6 4.800 3.200 7.400 8 8-4.800.6-7.400 3.200-8 8-.6-4.800-3.200-7.400-8-8 4.800-.6 7.400-3.200 8-8Z"/><path d="M19 3v3M20.500 4.500h-3"/>',
  compare: '<path d="M8 4v16M16 4v16M3 8h5M16 8h5M3 16h5M16 16h5"/>', share: '<circle cx="6" cy="12" r="2.500"/><circle cx="18" cy="6" r="2.500"/><circle cx="18" cy="18" r="2.500"/><path d="m8.200 10.800 7.600-3.600M8.200 13.200l7.600 3.600"/>',
  star: '<path d="m12 3 2.700 5.800 6.300.7-4.700 4.300 1.300 6.200L12 16.800 6.400 20l1.300-6.200L3 9.500l6.300-.7L12 3Z"/>', chevR: '<path d="m9 5 7 7-7 7"/>', chevD: '<path d="m5 9 7 7 7-7"/>', chevL: '<path d="m15 5-7 7 7 7"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>', plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>', arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  box: '<path d="M3.500 7.500 12 3l8.500 4.500v9L12 21l-8.500-4.500v-9Z"/><path d="m3.500 7.500 8.500 4.500 8.500-4.500M12 12v9"/>', truck: '<path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="17.500" r="1.800"/><circle cx="17" cy="17.500" r="1.800"/>',
  shield: '<path d="M12 3 4.500 6v5.500c0 4.600 3.100 8.200 7.500 9.500 4.400-1.300 7.500-4.900 7.500-9.500V6L12 3Z"/><path d="m9 12 2.200 2.200L15.500 10"/>', filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>', eye: '<path d="M2 12s3.500-6.500 10-6.500S22 12 22 12s-3.500 6.500-10 6.500S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4ZM13.500 6.500l4 4"/>', chart: '<path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6"/>', home: '<path d="M4 11 12 4l8 7v9H4v-9Z"/><path d="M10 20v-6h4v6"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8L3 12Z"/><circle cx="7.500" cy="8.500" r="1.200"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', mapPin: '<path d="M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11Z"/><circle cx="12" cy="10" r="2.500"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v8h14v-8M12 8v12M12 8c-2-4-6-3-5 0 .5 1.500 5 0 5 0Zm0 0c2-4 6-3 5 0-.5 1.500-5 0-5 0Z"/>',
  bag: '<path d="M5 8h14l1 12H4L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>', external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/>', link: '<path d="M10 14a4 4 0 0 0 5.700 0l3-3a4 4 0 0 0-5.700-5.700l-1 1M14 10a4 4 0 0 0-5.700 0l-3 3a4 4 0 0 0 5.700 5.700l1-1"/>',
  logout: '<path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9"/>', settings: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.500M12 18.500V21M3 12h2.500M18.500 12H21M5.600 5.600l1.800 1.800M16.600 16.600l1.800 1.800M5.600 18.400l1.800-1.800M16.600 7.400l1.800-1.800"/>',
};
export function icon(name, cls = "") {
  const wrap = document.createElement("span");
  wrap.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name] || ""}</svg>`;
  const el = wrap.firstChild;
  if (cls) el.setAttribute("class", cls);
  return el;
}
export const inr = (n, d = 0) => (n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
export const fmtDate = (iso, opts) => new Date(iso).toLocaleDateString("en-IN", opts || { day: "numeric", month: "short", year: "numeric" });
export const fmtDateTime = (iso) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const qs = (obj) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(obj)) if (v !== "" && v != null && v !== false) p.set(k, v === true ? "1" : v); const s = p.toString(); return s ? "?" + s : ""; };
export const COLOUR_HEX = { black: "#1c1c22", white: "#f3f3ef", blue: "#2f4bff", "sky blue": "#8ec5ff", sand: "#d8c3a5", beige: "#d9c7a3", olive: "#6b7a3a", navy: "#1d2a5c", grey: "#8a8f9c", indigo: "#2c3e8c", charcoal: "#3a3d46", maroon: "#7b1e3a", silver: "#c4c8d2", brown: "#6b4226", teal: "#1b8a8a", green: "#2e9e6b", purple: "#6b4de6", coral: "#e8604c" };
