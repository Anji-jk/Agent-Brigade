"use strict";
/*
 * "Token Cost by Run": one bar per run. Tokens mode: bars are output and input tokens on the left
 * axis. Cost mode: bars are dollars on the left axis. Both mode: the token bars on the left axis
 * and the cost as a line with a dot per run on its own right-hand $ axis; the two axis titles are
 * coloured like what they measure, and the line joins only runs that sit side by side on this
 * page. A run that failed has a red outline. Drawn as inline SVG with no library (ADR-0003).
 * Cache tokens are left out of the bars (they would flatten the other two) and shown in the tooltip.
 */
window.Brigade = window.Brigade || {};

Brigade.overviewChart = (function () {
  const { el } = Brigade.dom;
  const model = Brigade.overviewModel;
  const NS = "http://www.w3.org/2000/svg";
  const W = 760, H = 290, LEFT = 56, RIGHT = 16, RIGHT_BOTH = 60, TOP = 36, BOTTOM = 56, BAR = 64;

  function svg(tag, attrs, text) {
    const node = document.createElementNS(NS, tag);
    for (const [name, value] of Object.entries(attrs || {})) node.setAttribute(name, value);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function legend(mode, rows) {
    const box = el("div", "ov-legend");
    const tokens = [["ov-out", "Output tokens"], ["ov-in", "Input tokens (a tiny share: cache is counted apart)"]];
    const items = mode === "cost" ? [["ov-cost", "Cost"]] : mode === "both" ? [...tokens, ["ov-cost", "Cost (right axis)"]] : tokens;
    for (const [cls, text] of items) {
      const item = el("span", "ov-key");
      const swatch = el("span", "ov-swatch " + cls);
      item.append(swatch, document.createTextNode(text));
      box.append(item);
    }
    box.append(el("span", "ov-key muted", "Average " + model.money(model.average(rows)) + " per run"));
    return box;
  }

  /** Gridlines and the left axis; Both mode adds the $ axis on the right and a title over each axis. */
  function grid(root, bottom, edge, top, mode, costTop) {
    for (let i = 0; i <= 4; i++) {
      const y = bottom - (i * (bottom - TOP)) / 4;
      root.append(svg("line", { x1: LEFT, x2: W - edge, y1: y, y2: y, class: "ov-grid" }));
      root.append(svg("text", { x: LEFT - 6, y: y + 4, class: "ov-tick", "text-anchor": "end" }, mode === "cost" ? model.money((top * i) / 4) : model.compact((top * i) / 4)));
      if (mode === "both") root.append(svg("text", { x: W - edge + 6, y: y + 4, class: "ov-tick ov-tick-cost" }, model.money((costTop * i) / 4)));
    }
    if (mode === "cost") root.append(svg("text", { x: LEFT - 6, y: TOP - 12, class: "ov-axis ov-axis-cost", "text-anchor": "end" }, "Cost"));
    else root.append(svg("text", { x: LEFT - 6, y: TOP - 12, class: "ov-axis ov-axis-tokens", "text-anchor": "end" }, "Tokens"));
    if (mode === "both") root.append(svg("text", { x: W - edge + 6, y: TOP - 12, class: "ov-axis ov-axis-cost" }, "Cost"));
  }

  function tip(box, one) {
    box.replaceChildren(
      el("b", "", one.run_id),
      el("span", "", "Input " + model.num(one.input_tokens) + " · output " + model.num(one.output_tokens)),
      el("span", "", "Cost " + model.money(one.cost) + " · " + model.duration(one.wall_clock_seconds)),
      el("span", "", model.runNote(one)),
    );
  }

  function bars(group, one, mode, x, wide, bottom, scale) {
    if (mode === "cost") {
      group.append(svg("rect", { x, y: bottom - Math.max(1, one.cost * scale), width: wide, height: Math.max(1, one.cost * scale), class: "ov-cost" }));
      return bottom - Math.max(1, one.cost * scale);
    }
    const out = one.output_tokens * scale, inn = Math.max(1, one.input_tokens * scale);
    group.append(svg("rect", { x, y: bottom - inn, width: wide, height: inn, class: "ov-in" }), svg("rect", { x, y: bottom - inn - out, width: wide, height: out, class: "ov-out" }));
    return bottom - inn - out;
  }

  function render(host, rows, mode, onPick) {
    host.replaceChildren();
    if (!rows.length) {
      host.append(el("p", "empty", "No runs yet."));
      return;
    }
    const box = el("div", "ov-tip");
    box.hidden = true;
    const root = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "ov-svg", role: "img", "aria-label": "Tokens and cost by run" });
    const edge = mode === "both" ? RIGHT_BOTH : RIGHT;
    const top = model.niceMax(Math.max(...rows.map((r) => (mode === "cost" ? r.cost : r.input_tokens + r.output_tokens))));
    const costTop = model.niceMax(Math.max(...rows.map((r) => r.cost)));
    const bottom = H - BOTTOM, scale = (bottom - TOP) / top, slot = (W - LEFT - edge) / rows.length;
    const dotY = (one) => bottom - (one.cost / costTop) * (bottom - TOP);
    const roomy = rows.length <= 10, every = roomy ? 1 : Math.ceil(rows.length / 9);
    grid(root, bottom, edge, top, mode, costTop);
    rows.forEach((one, i) => {
      const mid = LEFT + (i + 0.5) * slot, wide = Math.min(BAR, slot * 0.7), x = mid - wide / 2;
      const group = svg("g", { class: "ov-bar", tabindex: 0, role: "button", "aria-label": "Open " + model.label(one) });
      group.append(svg("rect", { x: LEFT + i * slot, y: TOP - 20, width: slot, height: bottom - TOP + 20, class: "ov-hit" }));
      const peak = bars(group, one, mode, x, wide, bottom, scale);
      if (one.state === "failed") group.append(svg("rect", { x: x - 1, y: peak - 1, width: wide + 2, height: bottom - peak + 2, class: "ov-bad" }));
      if (roomy && mode !== "both") {
        const first = mode === "cost" ? model.money(one.cost) : model.compact(one.output_tokens) + " out";
        group.append(svg("text", { x: mid, y: peak - 6, class: "ov-mark", "text-anchor": "middle" }, first));
      }
      if (mode === "both") {
        group.append(svg("circle", { cx: mid, cy: dotY(one), r: 4.5, class: "ov-dot" }));
        if (roomy) group.append(svg("text", { x: mid, y: dotY(one) - 9, class: "ov-mark ov-mark-cost", "text-anchor": "middle" }, model.money(one.cost)));
      }
      if (i % every === 0) {
        root.append(svg("text", { x: mid, y: bottom + 16, class: "ov-name", "text-anchor": "middle" }, roomy ? model.label(one) : one.story_key));
        if (roomy && slot >= 170) root.append(svg("text", { x: mid, y: bottom + 32, class: "ov-tick", "text-anchor": "middle" }, model.runNote(one)));
      }
      const show = () => {
        tip(box, one);
        box.hidden = false;
        box.style.left = Math.min(Math.max((mid / W) * 100, 14), 86) + "%";
      };
      group.addEventListener("mouseenter", show);
      group.addEventListener("focus", show);
      group.addEventListener("mouseleave", () => (box.hidden = true));
      group.addEventListener("blur", () => (box.hidden = true));
      group.addEventListener("click", () => onPick(one));
      group.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onPick(one)));
      root.append(group);
    });
    if (mode === "both" && rows.length > 1) {
      const points = rows.map((one, i) => LEFT + (i + 0.5) * slot + "," + dotY(one)).join(" ");
      root.insertBefore(svg("polyline", { points, class: "ov-line" }), root.querySelector(".ov-bar"));
    }
    host.append(legend(mode, rows), root, box);
  }

  return { render };
})();
