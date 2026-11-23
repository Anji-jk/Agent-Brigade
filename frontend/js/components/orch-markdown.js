"use strict";
/*
 * A small markdown reader for the activity feed: headings, paragraphs, lists, tables, code
 * blocks, bold, italic, inline code. Everything is built from text with textContent, never
 * innerHTML, so nothing an agent wrote can run. Links show their words only and are not clickable.
 */
window.Brigade = window.Brigade || {};

Brigade.orchMarkdown = (function () {
  const { el } = Brigade.dom;
  const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*|\[[^\]\n]+\]\([^)\n]+\))/;
  const FENCE = /^\s*```/;
  const HEADING = /^(#{1,6})\s+(.*)$/;
  const BULLET = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
  const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
  const TABLE_ROW = /^\s*\|.*\|\s*$/;
  const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

  function inline(parent, text) {
    for (const part of text.split(INLINE)) {
      if (!part) continue;
      if (part[0] === "`" && part.length > 2) parent.append(el("code", "", part.slice(1, -1)));
      else if (part.startsWith("**") && part.length > 4) parent.append(el("strong", "", part.slice(2, -2)));
      else if (part[0] === "*" && part.length > 2) parent.append(el("em", "", part.slice(1, -1)));
      else if (part[0] === "[" && /^\[[^\]]+\]\(/.test(part)) parent.append(part.slice(1, part.indexOf("](")));
      else parent.append(part);
    }
    return parent;
  }

  const cells = (row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

  function table(rows) {
    const node = el("table", "orch-md-table");
    const head = el("tr");
    for (const text of cells(rows[0])) head.append(inline(el("th"), text));
    node.append(head);
    for (const row of rows.slice(2)) {
      const tr = el("tr");
      for (const text of cells(row)) tr.append(inline(el("td"), text));
      node.append(tr);
    }
    return node;
  }

  function list(items, ordered) {
    const node = el(ordered ? "ol" : "ul", "orch-md-list");
    for (const text of items) node.append(inline(el("li"), text));
    return node;
  }

  /** render(text) -> an element holding the formatted text. */
  function render(text) {
    const root = el("div", "orch-md");
    const rows = String(text || "").replace(/\r\n?/g, "\n").split("\n");
    let i = 0;
    while (i < rows.length) {
      const row = rows[i];
      let m;
      if (!row.trim()) i++;
      else if (FENCE.test(row)) {
        const code = [];
        for (i++; i < rows.length && !FENCE.test(rows[i]); i++) code.push(rows[i]);
        i++;
        root.append(el("pre", "orch-md-code", code.join("\n")));
      } else if ((m = HEADING.exec(row))) {
        root.append(inline(el("div", "orch-md-h orch-md-h" + Math.min(m[1].length, 4)), m[2]));
        i++;
      } else if (RULE.test(row)) {
        root.append(el("hr", "orch-md-rule"));
        i++;
      } else if (TABLE_ROW.test(row) && i + 1 < rows.length && TABLE_SEPARATOR.test(rows[i + 1])) {
        const grid = [];
        for (; i < rows.length && TABLE_ROW.test(rows[i]); i++) grid.push(rows[i]);
        root.append(table(grid));
      } else if (BULLET.test(row)) {
        const items = [];
        const ordered = /\d/.test(BULLET.exec(row)[1]);
        for (; i < rows.length && (m = BULLET.exec(rows[i])); i++) items.push(m[2]);
        root.append(list(items, ordered));
      } else {
        const para = [];
        for (; i < rows.length && rows[i].trim() && !FENCE.test(rows[i]) && !HEADING.test(rows[i]) && !BULLET.test(rows[i]); i++) para.push(rows[i].trim());
        root.append(inline(el("p", "orch-md-p"), para.join(" ")));
      }
    }
    return root;
  }

  return { render };
})();