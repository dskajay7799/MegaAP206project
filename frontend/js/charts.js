// Dependency-free SVG charts. Each chart is a <figure> with a text summary and a "view data" table, so it is readable without sight or colour.
import { h, svg, icon } from "./dom.js";

const PAL = ["#2540ff", "#0b1026", "#a9d93d", "#e8604c", "#6b4de6", "#1b8a8a", "#f4b400", "#8a8f9c"];
const nice = (max) => { if (max <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(max))), n = max / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p; };
const short = (n) => (n >= 1e7 ? (n / 1e7).toFixed(1) + "Cr" : n >= 1e5 ? (n / 1e5).toFixed(1) + "L" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k" : String(Math.round(n)));

function frame(title, summary, drawFn, tableRows, tableHead, { height = 240, empty = "" } = {}) {
  const host = h("div", { class: "chart-host", role: "img", "aria-label": `${title}. ${summary}` });
  const fig = h("figure", { class: "chart" }, h("figcaption", null, h("strong", null, title), h("span", { class: "muted small" }, summary)), empty ? h("p", { class: "chart-empty muted" }, icon("chart"), empty) : host);
  if (!empty) {
    const draw = () => { const w = Math.max(240, Math.floor(host.clientWidth || 320)); host.replaceChildren(drawFn(w, height)); };
    requestAnimationFrame(draw);
    if (window.ResizeObserver) { let last = 0; const ro = new ResizeObserver(() => { if (!fig.isConnected) return ro.disconnect(); const w = host.clientWidth; if (Math.abs(w - last) > 8) { last = w; draw(); } }); ro.observe(host); }
  }
  if (tableRows && tableRows.length) {
    fig.append(h("details", { class: "disc chart-data" }, h("summary", null, "View data as a table"), h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, tableHead.map((t, i) => h("th", { class: i ? "r" : "" }, t)))),
      h("tbody", null, tableRows.map((r) => h("tr", null, r.map((c, i) => h("td", { class: i ? "r num" : "" }, c)))))))));
  }
  return fig;
}

export function lineChart({ title, points, fmt = String, unit = "", area = true, markers = false, summary }) {
  const vals = points.map((p) => p.y);
  const total = vals.reduce((a, b) => a + b, 0);
  const sum = summary || (points.length ? `${points.length} points, from ${fmt(Math.min(...vals))} to ${fmt(Math.max(...vals))}.` : "");
  const none = !points.length || vals.every((v) => v === 0);
  return frame(title, none ? "" : sum, (w, ht) => {
    const L = 46, R = 12, T = 12, B = 30, iw = w - L - R, ih = ht - T - B, top = nice(Math.max(...vals)), n = points.length;
    const x = (i) => L + (n === 1 ? iw / 2 : (i / (n - 1)) * iw), y = (v) => T + ih - (v / top) * ih;
    const s = svg("svg", { viewBox: `0 0 ${w} ${ht}`, width: w, height: ht, "aria-hidden": "true" });
    for (let i = 0; i <= 4; i++) { const v = (top / 4) * i, yy = y(v); s.append(svg("line", { x1: L, x2: w - R, y1: yy, y2: yy, stroke: "#dedacf", "stroke-width": 1 }), svg("text", { x: L - 8, y: yy + 4, "text-anchor": "end", class: "ax" }, short(v))); }
    const step = Math.ceil(n / Math.max(2, Math.floor(iw / 70)));
    points.forEach((p, i) => { if (i % step === 0 || i === n - 1) s.append(svg("text", { x: x(i), y: ht - 8, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle", class: "ax" }, p.x)); });
    const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.y).toFixed(1)}`).join("");
    if (area && n > 1) s.append(svg("path", { d: `${d}L${x(n - 1)} ${T + ih}L${x(0)} ${T + ih}Z`, fill: "#2540ff", opacity: ".1" }));
    s.append(svg("path", { d, fill: "none", stroke: "#2540ff", "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    points.forEach((p, i) => { if (markers || n <= 12) s.append(svg("circle", { cx: x(i), cy: y(p.y), r: 4, fill: "#fff", stroke: "#2540ff", "stroke-width": 2 }, svg("title", null, `${p.x}: ${fmt(p.y)}${unit}`))); });
    return s;
  }, points.map((p) => [p.x, fmt(p.y) + unit]), ["Date", "Value"], { empty: none ? "Nothing recorded yet." : "" });
}

export function barChart({ title, data, fmt = String, color, horizontal = false, summary, colors }) {
  const none = !data.length || data.every((d) => d.value === 0);
  const sum = summary || (data.length ? `Highest: ${[...data].sort((a, b) => b.value - a.value)[0].label} (${fmt([...data].sort((a, b) => b.value - a.value)[0].value)}).` : "");
  return frame(title, none ? "" : sum, (w, ht) => {
    if (horizontal) {
      const rowH = 34, H = data.length * rowH + 8, labW = Math.min(150, w * .38), max = nice(Math.max(...data.map((d) => d.value)));
      const s = svg("svg", { viewBox: `0 0 ${w} ${H}`, width: w, height: H, "aria-hidden": "true" });
      data.forEach((d, i) => {
        const bw = Math.max(2, ((w - labW - 56) * d.value) / max), yy = 4 + i * rowH;
        const lab = d.label.length > 22 ? d.label.slice(0, 21) + "…" : d.label;
        s.append(svg("text", { x: 0, y: yy + 20, class: "ax lab" }, lab, svg("title", null, d.label)), svg("rect", { x: labW, y: yy + 6, width: bw, height: 18, rx: 5, fill: (colors && colors[i]) || color || PAL[0] }), svg("text", { x: labW + bw + 8, y: yy + 20, class: "ax val" }, fmt(d.value)));
      });
      return s;
    }
    const L = 40, R = 8, T = 14, B = 44, iw = w - L - R, ih = ht - T - B, top = nice(Math.max(...data.map((d) => d.value))), bw = Math.min(54, (iw / data.length) * .62);
    const s = svg("svg", { viewBox: `0 0 ${w} ${ht}`, width: w, height: ht, "aria-hidden": "true" });
    for (let i = 0; i <= 4; i++) { const v = (top / 4) * i, yy = T + ih - (v / top) * ih; s.append(svg("line", { x1: L, x2: w - R, y1: yy, y2: yy, stroke: "#dedacf" }), svg("text", { x: L - 6, y: yy + 4, "text-anchor": "end", class: "ax" }, short(v))); }
    data.forEach((d, i) => {
      const cx = L + (iw / data.length) * (i + .5), bh = (d.value / top) * ih;
      s.append(svg("rect", { x: cx - bw / 2, y: T + ih - bh, width: bw, height: Math.max(0, bh), rx: 6, fill: (colors && colors[i]) || color || PAL[0] }, svg("title", null, `${d.label}: ${fmt(d.value)}`)));
      if (d.value) s.append(svg("text", { x: cx, y: T + ih - bh - 5, "text-anchor": "middle", class: "ax val" }, short(d.value)));
      const words = d.label.split(" "), l1 = words.slice(0, Math.ceil(words.length / 2)).join(" "), l2 = words.slice(Math.ceil(words.length / 2)).join(" ");
      s.append(svg("text", { x: cx, y: ht - 24, "text-anchor": "middle", class: "ax" }, l1.length > 12 ? l1.slice(0, 11) + "…" : l1), svg("text", { x: cx, y: ht - 11, "text-anchor": "middle", class: "ax" }, l2.length > 12 ? l2.slice(0, 11) + "…" : l2));
    });
    return s;
  }, data.map((d) => [d.label, fmt(d.value)]), ["Label", "Value"], { height: horizontal ? 0 : 250, empty: none ? "Nothing recorded yet." : "" });
}

export function donut({ title, data, fmt = String, summary }) {
  const total = data.reduce((a, d) => a + d.value, 0);
  const sum = summary || (total ? `${data.length} groups, ${fmt(total)} in total. Largest: ${[...data].sort((a, b) => b.value - a.value)[0].label}.` : "");
  return frame(title, sum, (w) => {
    const size = Math.min(w, 220), r = size / 2 - 8, cx = size / 2, cy = size / 2, rw = 26;
    const s = svg("svg", { viewBox: `0 0 ${size} ${size}`, width: size, height: size, "aria-hidden": "true", class: "donut-svg" });
    let a0 = -Math.PI / 2;
    data.filter((d) => d.value > 0).forEach((d, i) => {
      const a1 = a0 + (d.value / total) * Math.PI * 2 - (data.length > 1 ? .02 : 0), large = a1 - a0 > Math.PI ? 1 : 0;
      const p = (a, rr) => `${(cx + rr * Math.cos(a)).toFixed(2)} ${(cy + rr * Math.sin(a)).toFixed(2)}`;
      s.append(svg("path", { d: data.filter((x) => x.value > 0).length === 1 ? `M${cx} ${cy - r}A${r} ${r} 0 1 1 ${cx - .01} ${cy - r}` : `M${p(a0, r)}A${r} ${r} 0 ${large} 1 ${p(a1, r)}`, fill: "none", stroke: PAL[i % PAL.length], "stroke-width": rw }, svg("title", null, `${d.label}: ${fmt(d.value)}`)));
      a0 += (d.value / total) * Math.PI * 2;
    });
    s.append(svg("text", { x: cx, y: cy + 6, "text-anchor": "middle", class: "donut-total" }, short(total)));
    const legend = h("ul", { class: "legend" }, data.map((d, i) => h("li", null, h("i", { style: { background: PAL[i % PAL.length] } }), h("span", null, d.label), h("b", { class: "num" }, fmt(d.value)))));
    const box = h("div", { class: "donut-box" }, s, legend);
    return box;
  }, data.map((d) => [d.label, fmt(d.value)]), ["Group", "Value"], { empty: total ? "" : "Nothing recorded yet." });
}

export function radar({ title, axes, series, summary }) {
  return frame(title, summary || "Each axis is scaled relative to the compared products only (1 = best of the group).", (w) => {
    const size = Math.min(w, 380), cx = size / 2, cy = size / 2 + 4, R = size / 2 - 58, n = axes.length;
    const s = svg("svg", { viewBox: `0 0 ${size} ${size + 8}`, width: size, height: size + 8, "aria-hidden": "true", class: "radar-svg" });
    const pt = (i, v) => [cx + R * v * Math.sin((i / n) * Math.PI * 2), cy - R * v * Math.cos((i / n) * Math.PI * 2)];
    [.25, .5, .75, 1].forEach((g) => s.append(svg("polygon", { points: axes.map((_, i) => pt(i, g).map((x) => x.toFixed(1)).join(",")).join(" "), fill: "none", stroke: "#dedacf" })));
    axes.forEach((a, i) => { const [x, y] = pt(i, 1), [lx, ly] = pt(i, 1.2); s.append(svg("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: "#dedacf" }), svg("text", { x: lx, y: ly + 4, "text-anchor": lx < cx - 8 ? "end" : lx > cx + 8 ? "start" : "middle", class: "ax" }, a.label.length > 16 ? a.label.slice(0, 15) + "…" : a.label)); });
    series.forEach((se, k) => {
      const c = PAL[k % PAL.length];
      s.append(svg("polygon", { points: se.values.map((v, i) => pt(i, Math.max(.04, v)).map((x) => x.toFixed(1)).join(",")).join(" "), fill: c, "fill-opacity": ".14", stroke: c, "stroke-width": 2.2, "stroke-linejoin": "round" }));
      se.values.forEach((v, i) => { const [x, y] = pt(i, Math.max(.04, v)); s.append(svg("circle", { cx: x, cy: y, r: 3.5, fill: c }, svg("title", null, `${se.name} · ${axes[i].label}: ${axes[i].raw ? axes[i].raw[k] : v.toFixed(2)}`))); });
    });
    return h("div", { class: "radar-box" }, s, h("ul", { class: "legend" }, series.map((se, k) => h("li", null, h("i", { style: { background: PAL[k % PAL.length] } }), h("span", null, se.name)))));
  }, series.flatMap((se, k) => axes.map((a, i) => [`${se.name} · ${a.label}`, a.raw ? String(a.raw[k]) : se.values[i].toFixed(2)])), ["Product · measure", "Value"]);
}
